import streamlit as st
import pandas as pd
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

# ── Constants ────────────────────────────────────────────────────────────────

TZ = ZoneInfo('America/Toronto')

MULTIPLIERS = {
    'Walk': 3.0,
    'Run': 3.0,
    'Swim': 5.0,
    'Ride': 2.0,
    'Virtual Ride': 2.0,
}

CATEGORIES = {
    'On Foot': ['Walk', 'Run'],
    'Swim':    ['Swim'],
    'Ride':    ['Ride', 'Virtual Ride'],
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def load_and_filter(files, start_dt, end_dt):
    """Load uploaded CSVs, filter by activity type / date, compute scores."""
    frames = []
    for f in files:
        df = pd.read_csv(f, thousands=',')
        df = df.rename(columns={' \"Type\"': 'Type'})
        df = df[['Type', 'Name', 'Date', 'Distance', 'Unit']]
        df = df[df['Type'].isin(MULTIPLIERS)]
        df = df[df['Distance'].notna()]

        df['Date'] = pd.to_datetime(df['Date'], format='ISO8601', utc=True)
        df = df[(df['Date'] >= start_dt) & (df['Date'] <= end_dt)]

        df['Distance'] = pd.to_numeric(df['Distance'], errors='coerce')
        df = df[df['Distance'].notna()]

        # metres → km
        df.loc[df['Unit'] == 'm', 'Distance'] /= 1000

        df['Score'] = df.apply(lambda r: MULTIPLIERS[r['Type']] * r['Distance'], axis=1)
        frames.append(df)

    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


def make_tz_aware(d: date, end_of_day=False):
    t = time.max if end_of_day else time.min
    return datetime.combine(d, t).replace(tzinfo=TZ)

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="Synthesis WAC Calculator", page_icon="🏃", layout="wide")

st.title("🏃 Synthesis Walk Across Canada")
st.caption("Upload one or more Strava export CSVs, pick a date range, and get your results.")

# ── Sidebar: file upload + date range ────────────────────────────────────────

with st.sidebar:
    st.header("⚙️ Settings")
    uploaded = st.file_uploader(
        "Upload CSV file(s)", type="csv", accept_multiple_files=True
    )
    st.divider()
    today = date.today()
    start = st.date_input("Start date", value=today)
    end   = st.date_input("End date",   value=today)
    run   = st.button("Calculate", type="primary", use_container_width=True)

# ── Main area ─────────────────────────────────────────────────────────────────

if not run:
    st.info("Upload at least one CSV and hit **Calculate** in the sidebar.")
    st.stop()

if not uploaded:
    st.error("Please upload at least one CSV file.")
    st.stop()

if start > end:
    st.error("Start date must be before end date.")
    st.stop()

start_dt = make_tz_aware(start, end_of_day=False)
end_dt   = make_tz_aware(end,   end_of_day=True)

df = load_and_filter(uploaded, start_dt, end_dt)

if df is None or df.empty:
    st.warning("No matching activities found in that date range.")
    st.stop()

# ── Team Score ────────────────────────────────────────────────────────────────

team_score = df['Score'].sum()

st.header("🎯 Team Score")
st.metric("Total adjusted distance (km)", f"{team_score:,.2f}")

st.divider()

# ── Leaderboards ──────────────────────────────────────────────────────────────

st.header("🏆 Leaderboards")

tabs = st.tabs(["Overall"] + list(CATEGORIES.keys()))

# Overall
overall = (
    df.groupby('Name')['Score']
    .sum()
    .sort_values(ascending=False)
    .reset_index()
    .rename(columns={'Score': 'Adjusted Distance (km)'})
)
overall.index += 1  # 1-based rank
with tabs[0]:
    st.dataframe(overall, use_container_width=True)

# Per category
for i, (cat, types) in enumerate(CATEGORIES.items()):
    cat_df = df[df['Type'].isin(types)]
    if cat_df.empty:
        with tabs[i + 1]:
            st.info(f"No {cat} activities in this period.")
        continue
    cat_lb = (
        cat_df.groupby('Name')['Score']
        .sum()
        .sort_values(ascending=False)
        .reset_index()
        .rename(columns={'Score': 'Adjusted Distance (km)'})
    )
    cat_lb.index += 1
    with tabs[i + 1]:
        st.dataframe(cat_lb, use_container_width=True)

st.divider()

# ── Raw activity log ──────────────────────────────────────────────────────────

with st.expander("📋 Raw activity log"):
    display_df = df[['Name', 'Type', 'Date', 'Distance', 'Score']].copy()
    display_df['Date'] = display_df['Date'].dt.tz_convert(TZ).dt.strftime('%Y-%m-%d %H:%M')
    display_df = display_df.rename(columns={
        'Distance': 'Distance (km)',
        'Score': 'Adjusted Distance (km)'
    }).sort_values('Date', ascending=False).reset_index(drop=True)
    st.dataframe(display_df, use_container_width=True)
