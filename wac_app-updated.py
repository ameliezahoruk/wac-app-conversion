import streamlit as st
import pandas as pd
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

# ── Constants ────────────────────────────────────────────────────────────────

TZ = ZoneInfo('America/Toronto')

BASE_MULTIPLIERS = {
    'Walk': 1.0,
    'Run': 1.0,
    'Swim': 5.0,
    'Ride': 1.0,
    'Virtual Ride': 1.0,
}

CATEGORIES = {
    'On Foot': ['Walk', 'Run'],
    'Swim':    ['Swim'],
    'Ride':    ['Ride', 'Virtual Ride'],
}

TEAM_NAMES = ['1A24', '2A18', '3A12', '4A12']

# ── Helpers ──────────────────────────────────────────────────────────────────

def make_tz_aware(d: date, end_of_day=False):
    t = time.max if end_of_day else time.min
    return datetime.combine(d, t).replace(tzinfo=TZ)


def get_multiplier(activity_type, activity_date, bonus_periods):
    base = BASE_MULTIPLIERS.get(activity_type, 1.0)
    bonus = 0.0
    for period in bonus_periods:
        if (period['start'] <= activity_date <= period['end']
                and activity_type in period['types']):
            bonus = max(bonus, period['bonus'])
    return base + bonus


def load_and_score(files, start_dt, end_dt, bonus_periods):
    frames = []
    for f in files:
        df = pd.read_csv(f, thousands=',')
        df = df.rename(columns={' \"Type\"': 'Type'})
        df = df[['Type', 'Name', 'Date', 'Distance', 'Unit']]
        df = df[df['Type'].isin(BASE_MULTIPLIERS)]
        df = df[df['Distance'].notna()]

        df['Date'] = pd.to_datetime(df['Date'], format='ISO8601', utc=True)
        df = df[(df['Date'] >= start_dt) & (df['Date'] <= end_dt)]

        df['Distance'] = pd.to_numeric(df['Distance'], errors='coerce')
        df = df[df['Distance'].notna()]
        df.loc[df['Unit'] == 'm', 'Distance'] /= 1000

        df['Multiplier'] = df.apply(
            lambda r: get_multiplier(r['Type'], r['Date'], bonus_periods), axis=1
        )
        df['Score'] = df['Distance'] * df['Multiplier']
        frames.append(df)

    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="Synthesis WAC", page_icon="🏃", layout="wide")
st.title("🏃 Synthesis Walk Across Canada")

setup_tab, results_tab = st.tabs(["⚙️ Setup", "📊 Results"])

# ═══════════════════════════════════════════════════════════════════════════════
# SETUP TAB
# ═══════════════════════════════════════════════════════════════════════════════

with setup_tab:

    # ── Date range ────────────────────────────────────────────────────────────
    st.subheader("Date Range")
    col1, col2 = st.columns(2)
    with col1:
        start = st.date_input("Start date", value=date.today())
    with col2:
        end = st.date_input("End date", value=date.today())

    st.divider()

    # ── Team CSV uploads ──────────────────────────────────────────────────────
    st.subheader("Team Data")
    st.caption("Upload one or more CSVs per team. Individuals compete cohort-wide regardless of team.")

    team_files = {}
    team_cols = st.columns(4)
    for i, (col, name) in enumerate(zip(team_cols, TEAM_NAMES)):
        with col:
            st.markdown(f"**{name}**")
            team_files[name] = st.file_uploader(
                f"CSV(s) for {name}", type="csv",
                accept_multiple_files=True,
                key=f"upload_{i}",
                label_visibility="collapsed"
            )

    st.divider()

    # ── Bonus multiplier periods ──────────────────────────────────────────────
    st.subheader("⚡ Bonus Multiplier Periods")
    st.caption("Activities in these date ranges earn an extra multiplier on top of the base. Applies to both team and individual scores.")

    if 'bonus_periods' not in st.session_state:
        st.session_state.bonus_periods = []

    with st.expander("Add a bonus period", expanded=False):
        bc1, bc2, bc3 = st.columns(3)
        with bc1:
            bp_start = st.date_input("Bonus start", value=date.today(), key="bp_start")
            bp_end   = st.date_input("Bonus end",   value=date.today(), key="bp_end")
        with bc2:
            bp_types = st.multiselect(
                "Activity types",
                options=list(BASE_MULTIPLIERS.keys()),
                default=['Walk', 'Run'],
                key="bp_types"
            )
        with bc3:
            bp_bonus = st.number_input("Bonus multiplier (+)", min_value=0.0, value=1.0, step=0.5, key="bp_bonus")
            if bp_types:
                examples = ', '.join(
                    f"{t}: {BASE_MULTIPLIERS[t]}× → {BASE_MULTIPLIERS[t] + bp_bonus}×"
                    for t in bp_types[:2]
                )
                st.caption(examples)

        if st.button("➕ Add bonus period"):
            if bp_start > bp_end:
                st.error("Bonus start must be before bonus end.")
            elif not bp_types:
                st.error("Select at least one activity type.")
            else:
                st.session_state.bonus_periods.append({
                    'start': make_tz_aware(bp_start),
                    'end':   make_tz_aware(bp_end, end_of_day=True),
                    'types': bp_types,
                    'bonus': bp_bonus,
                })
                st.success("Bonus period added!")

    if st.session_state.bonus_periods:
        st.markdown("**Active bonus periods:**")
        for i, p in enumerate(st.session_state.bonus_periods):
            cols = st.columns([5, 1])
            with cols[0]:
                types_str = ', '.join(p['types'])
                start_str = p['start'].strftime('%b %d')
                end_str   = p['end'].strftime('%b %d')
                st.markdown(f"- **{start_str} – {end_str}** | {types_str} | +{p['bonus']}×")
            with cols[1]:
                if st.button("✕", key=f"del_bp_{i}"):
                    st.session_state.bonus_periods.pop(i)
                    st.rerun()

    st.divider()

    # ── Bonus kilometres ──────────────────────────────────────────────────────
    st.subheader("🎁 Bonus Kilometres")
    st.caption("Added to team totals only — does not affect individual leaderboards.")

    if 'bonus_km' not in st.session_state:
        st.session_state.bonus_km = {name: [] for name in TEAM_NAMES}

    bk_cols = st.columns(4)
    for i, (col, name) in enumerate(zip(bk_cols, TEAM_NAMES)):
        with col:
            st.markdown(f"**{name}**")
            with st.expander("Add bonus km"):
                mode = st.radio("Mode", ["Flat amount", "Per student"], key=f"bk_mode_{i}", horizontal=True)
                if mode == "Flat amount":
                    flat = st.number_input("km to add", min_value=0.0, value=0.0, step=1.0, key=f"bk_flat_{i}")
                    if st.button("Add", key=f"bk_add_{i}"):
                        st.session_state.bonus_km[name].append({'type': 'flat', 'km': flat})
                        st.rerun()
                else:
                    n_students = st.number_input("# students", min_value=1, value=1, step=1, key=f"bk_n_{i}")
                    km_each    = st.number_input("km per student", min_value=0.0, value=0.0, step=0.5, key=f"bk_each_{i}")
                    if st.button("Add", key=f"bk_add2_{i}"):
                        st.session_state.bonus_km[name].append({
                            'type': 'per_student',
                            'n': n_students,
                            'km_each': km_each,
                            'km': n_students * km_each,
                        })
                        st.rerun()

            entries = st.session_state.bonus_km[name]
            if entries:
                for j, b in enumerate(entries):
                    ecols = st.columns([3, 1])
                    with ecols[0]:
                        if b['type'] == 'flat':
                            st.caption(f"+{b['km']:.1f} km (flat)")
                        else:
                            st.caption(f"+{b['km']:.1f} km ({b['n']} × {b['km_each']:.1f})")
                    with ecols[1]:
                        if st.button("✕", key=f"del_bk_{i}_{j}"):
                            st.session_state.bonus_km[name].pop(j)
                            st.rerun()
                total = sum(b['km'] for b in entries)
                st.markdown(f"**Total: +{total:.1f} km**")

    st.divider()
    run = st.button("▶ Calculate Results", type="primary", use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════════════
# RESULTS TAB
# ═══════════════════════════════════════════════════════════════════════════════

with results_tab:

    if not run:
        st.info("Configure settings in the **Setup** tab and hit **Calculate Results**.")
        st.stop()

    if start > end:
        st.error("Start date must be before end date.")
        st.stop()

    start_dt = make_tz_aware(start)
    end_dt   = make_tz_aware(end, end_of_day=True)
    bonus_periods = st.session_state.bonus_periods

    team_dfs = {}
    for name in TEAM_NAMES:
        files = team_files.get(name, [])
        if files:
            df = load_and_score(files, start_dt, end_dt, bonus_periods)
            if df is not None and not df.empty:
                df['Team'] = name
                team_dfs[name] = df

    if not team_dfs:
        st.warning("No data found. Upload CSVs and check your date range.")
        st.stop()

    all_df = pd.concat(team_dfs.values(), ignore_index=True)

    # ── Team Competition ──────────────────────────────────────────────────────
    st.header("🏅 Team Competition")

    team_scores = []
    for name in TEAM_NAMES:
        activity_score = team_dfs[name]['Score'].sum() if name in team_dfs else 0.0
        bonus = sum(b['km'] for b in st.session_state.bonus_km.get(name, []))
        team_scores.append({
            'Team': name,
            'Activity Score (km)': round(activity_score, 2),
            'Bonus km': round(bonus, 2),
            'Total Score (km)': round(activity_score + bonus, 2),
        })

    team_df = (
        pd.DataFrame(team_scores)
        .sort_values('Total Score (km)', ascending=False)
        .reset_index(drop=True)
    )
    team_df.index += 1

    medals = ['🥇', '🥈', '🥉', '4️⃣']
    metric_cols = st.columns(len(team_df))
    for i, (col, row) in enumerate(zip(metric_cols, team_df.itertuples())):
        with col:
            delta_str = f"+{row._3:.1f} bonus km" if row._3 > 0 else None
            st.metric(f"{medals[i]} {row.Team}", f"{row._4:,.2f} km", delta=delta_str)

    st.dataframe(team_df, use_container_width=True)

    st.divider()

    # ── Individual Leaderboards ───────────────────────────────────────────────
    st.header("🏆 Individual Leaderboards (Cohort-Wide)")
    st.caption("All participants compete together regardless of team.")

    def make_leaderboard(df, types=None):
        sub = df[df['Type'].isin(types)] if types else df
        if sub.empty:
            return None
        lb = (
            sub.groupby(['Name', 'Team'])['Score']
            .sum()
            .sort_values(ascending=False)
            .reset_index()
            .rename(columns={'Score': 'Adjusted Distance (km)'})
        )
        lb['Adjusted Distance (km)'] = lb['Adjusted Distance (km)'].round(2)
        lb.index += 1
        return lb

    ind_tabs = st.tabs(["Overall"] + list(CATEGORIES.keys()))

    with ind_tabs[0]:
        lb = make_leaderboard(all_df)
        if lb is not None:
            st.dataframe(lb, use_container_width=True)

    for i, (cat, types) in enumerate(CATEGORIES.items()):
        with ind_tabs[i + 1]:
            lb = make_leaderboard(all_df, types)
            if lb is not None:
                st.dataframe(lb, use_container_width=True)
            else:
                st.info(f"No {cat} activities in this period.")

    st.divider()

    # ── Raw log ───────────────────────────────────────────────────────────────
    with st.expander("📋 Raw activity log"):
        log = all_df[['Team', 'Name', 'Type', 'Date', 'Distance', 'Multiplier', 'Score']].copy()
        log['Date'] = log['Date'].dt.tz_convert(TZ).dt.strftime('%Y-%m-%d %H:%M')
        log = log.rename(columns={'Distance': 'Distance (km)', 'Score': 'Adjusted Distance (km)'})
        log = log.sort_values('Date', ascending=False).reset_index(drop=True)
        st.dataframe(log, use_container_width=True)
