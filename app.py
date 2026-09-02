import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# Set page config
st.set_page_config(page_title="Seismica Journal Dashboard", layout="wide")

st.title("📊 Seismica Journal Dashboard")
st.markdown("Live bibliometric insights powered by the OpenAlex API.")

SOURCE_ID = "s4387284412"

# 1. Fetch Data from OpenAlex API
@st.cache_data(ttl=3600)
def fetch_seismica_data(source_id):
    base_url = "https://api.openalex.org/works"
    
    # Safe retrieval of secrets without breaking if secrets.toml is missing
    api_key = None
    try:
        if "OPENALEX_API_KEY" in st.secrets:
            api_key = st.secrets["OPENALEX_API_KEY"]
    except Exception:
        api_key = None

    headers = {
        "User-Agent": "SeismicaDashboard/1.0 (mailto:admin@example.com)"
    }
    
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    params = {
        "filter": f"primary_location.source.id:{source_id}",
        "per_page": 100,
        "cursor": "*"
    }
    
    if api_key:
        params["api_key"] = api_key
    
    all_works = []
    
    while True:
        try:
            response = requests.get(base_url, headers=headers, params=params, timeout=15)
            if response.status_code != 200:
                st.error(f"OpenAlex API returned HTTP status code: {response.status_code}")
                break
            
            data = response.json()
            results = data.get("results", [])
            if not results:
                break
            
            all_works.extend(results)
            
            # Pagination cursor handling
            next_cursor = data.get("meta", {}).get("next_cursor")
            if not next_cursor or next_cursor == params["cursor"]:
                break
            params["cursor"] = next_cursor
            
        except Exception as e:
            st.error(f"Error fetching data from API: {e}")
            break
        
    return all_works

with st.spinner("Fetching data from OpenAlex..."):
    works = fetch_seismica_data(SOURCE_ID)

if not works:
    st.error("No data found or failed to fetch data from OpenAlex.")
    st.stop()

# 2. Process Data into Pandas DataFrames
processed_data = []
counts_by_year_list = []
institution_list = []
country_code_list = []


for w in works:
    # Extract primary topic safely
    primary_topic_data = w.get("primary_topic")
    if isinstance(primary_topic_data, dict):
        primary_topic = primary_topic_data.get("display_name", "Unknown")
    else:
        topics = [t.get("display_name") for t in w.get("topics", []) if isinstance(t, dict)]
        primary_topic = topics[0] if topics else "Unknown"
    
    # Extract first author
    authorships = w.get("authorships", [])
    if authorships and isinstance(authorships[0], dict):
        author_info = authorships[0].get("author", {})
        author_name = author_info.get("display_name", "Unknown") if isinstance(author_info, dict) else "Unknown"
    else:
        author_name = "Unknown"

    # Extract institutional affiliations for all authors
    for auth in authorships:
            if isinstance(auth, dict):
                for inst in auth.get("institutions", []):
                    if isinstance(inst, dict):
                        if inst.get("display_name"):
                            institution_list.append(inst.get("display_name"))
                        if inst.get("country_code"):
                            country_code_list.append(inst.get("country_code").upper())
    
    pub_year = w.get("publication_year")
    
    processed_data.append({
        "id": w.get("id"),
        "title": w.get("title", "Untitled Work"),
        "author": author_name,
        "publication_year": pub_year,
        "publication_date": w.get("publication_date"),
        "cited_by_count": w.get("cited_by_count", 0),
        "type": w.get("type", "Unknown"),
        "doi": w.get("doi"),
        "primary_topic": primary_topic,
        "author_count": len(authorships)
    })

    # Collect year-by-year citation breakdown for 2-year citedness calculation
    for cby in w.get("counts_by_year", []):
        counts_by_year_list.append({
            "work_id": w.get("id"),
            "publication_year": pub_year,
            "citation_year": cby.get("year"),
            "citations": cby.get("cited_by_count", 0)
        })

df = pd.DataFrame(processed_data)
cby_df = pd.DataFrame(counts_by_year_list)
inst_df = pd.DataFrame({"institution": institution_list})
country_df = pd.DataFrame({"country_code": country_code_list})

# --- DASHBOARD METRICS ---
total_papers = len(df)
total_citations = int(df["cited_by_count"].sum())
avg_citations = round(df["cited_by_count"].mean(), 2) if total_papers > 0 else 0.0

col1, col2, col3 = st.columns(3)
col1.metric("Total Publications", total_papers)
col2.metric("Total Citations", total_citations)
col3.metric("Avg. Citations per Paper", avg_citations)

st.markdown("---")

# --- 2-YEAR MEAN CITEDNESS SECTION (2024 & 2025 ONLY) ---
st.subheader("📈 2-Year Mean Citedness (2024 & 2025)")
st.markdown(
    "Measures the average number of citations received in 2024 and 2025 by items published in *Seismica* during the prior two years (analogous to 2-Year Journal Impact Factor)."
)

target_years = [2024, 2025]
citedness_records = []

if not cby_df.empty:
    for eval_year in target_years:
        p1, p2 = eval_year - 1, eval_year - 2
        
        window_works = df[df["publication_year"].isin([p1, p2])]
        num_papers_in_window = len(window_works)
        
        if num_papers_in_window > 0:
            window_work_ids = window_works["id"].tolist()
            
            cits_in_eval_year = cby_df[
                (cby_df["work_id"].isin(window_work_ids)) & 
                (cby_df["citation_year"] == eval_year)
            ]["citations"].sum()
            
            mean_citedness = round(cits_in_eval_year / num_papers_in_window, 3)
        else:
            cits_in_eval_year = 0
            mean_citedness = 0.0
            
        citedness_records.append({
            "Evaluation Year": eval_year,
            "Window Years": f"{p2}-{p1}",
            "Papers in Window": num_papers_in_window,
            "Citations in Year": cits_in_eval_year,
            "2-Yr Mean Citedness": mean_citedness
        })

citedness_df = pd.DataFrame(citedness_records)

if not citedness_df.empty:
    # 1. Top Section: Metric KPI + Data Table side-by-side
    metric_col, table_col = st.columns([1, 2])
    
    with metric_col:
        latest_row = citedness_df.iloc[-1]
        st.metric(
            label=f"2-Yr Mean Citedness ({latest_row['Evaluation Year']})", 
            value=latest_row["2-Yr Mean Citedness"],
            help=f"Based on {latest_row['Citations in Year']} citations received in {latest_row['Evaluation Year']} for {latest_row['Papers in Window']} papers published in {latest_row['Window Years']}."
        )

    with table_col:
        st.dataframe(citedness_df, use_container_width=True, hide_index=True)

st.markdown("---")

# --- VISUALIZATIONS ---
chart_col1, inst_col = st.columns(2)

with chart_col1:
    st.subheader("📊 Publications Over Time by Document Type")
    
    # Group by year and document type
    pub_type_df = df.dropna(subset=["publication_year"]).groupby(
        ["publication_year", "type"]
    ).size().reset_index(name="Count")
    pub_type_df["publication_year"] = pub_type_df["publication_year"].astype(int)
    
    # Create stacked bar chart using the same color palette as pie chart
    fig_pub_stack = px.bar(
        pub_type_df,
        x="publication_year",
        y="Count",
        color="type",
        # title="Publications Over Time (Breakdown by Document Type)",
        color_discrete_sequence=px.colors.qualitative.Safe,
        labels={"publication_year": "Year", "Count": "Number of Publications", "type": "Document Type"}
    )
    
    fig_pub_stack.update_layout(
        barmode="stack",
        xaxis=dict(dtick=1),
        yaxis=dict(title="Number of Publications"),
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig_pub_stack, use_container_width=True)

with inst_col:
    st.subheader("🏛️ Top Institutional Affiliations")
    if not inst_df.empty:
        top_inst_df = inst_df["institution"].value_counts().reset_index().head(10)
        top_inst_df.columns = ["Institution", "Count"]
        fig_inst = px.bar(top_inst_df, x="Count", y="Institution", orientation="h", color_discrete_sequence=["#4682B4"])
        fig_inst.update_layout(yaxis={'categoryorder': 'total ascending'}, margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig_inst, use_container_width=True)
    else:
        st.info("No institutional metadata available.")

st.markdown("---")

# --- AUTHOR GEOGRAPHIC DISTRIBUTION SECTION (FIRST AUTHOR ONLY) ---
st.subheader("🌍 Geographic Distribution of First Author Affiliations")

first_author_country_codes = []

for w in works:
    authorships = w.get("authorships", [])
    if authorships and isinstance(authorships[0], dict):
        first_author = authorships[0]
        for inst in first_author.get("institutions", []):
            if isinstance(inst, dict) and inst.get("country_code"):
                first_author_country_codes.append(inst.get("country_code").upper())

first_author_country_df = pd.DataFrame({"country_code": first_author_country_codes})

if not first_author_country_df.empty:
    # ISO-2 to ISO-3 lookup dictionary
    ISO2_TO_ISO3 = {
        'AF': 'AFG', 'AL': 'ALB', 'DZ': 'DZA', 'AS': 'ASM', 'AD': 'AND', 'AO': 'AGO', 'AI': 'AIA', 'AQ': 'ATA',
        'AG': 'ATG', 'AR': 'ARG', 'AM': 'ARM', 'AW': 'ABW', 'AU': 'AUS', 'AT': 'AUT', 'AZ': 'AZE', 'BS': 'BHS',
        'BH': 'BHR', 'BD': 'BGD', 'BB': 'BRB', 'BY': 'BLR', 'BE': 'BEL', 'BZ': 'BLZ', 'BJ': 'BEN', 'BM': 'BMU',
        'BT': 'BTN', 'BO': 'BOL', 'BA': 'BIH', 'BW': 'BWA', 'BR': 'BRA', 'BN': 'BRN', 'BG': 'BGR', 'BF': 'BFA',
        'BI': 'BDI', 'KH': 'KHM', 'CM': 'CMR', 'CA': 'CAN', 'CV': 'CPV', 'KY': 'CYM', 'CF': 'CAF', 'TD': 'TCD',
        'CL': 'CHL', 'CN': 'CHN', 'CO': 'COL', 'KM': 'COM', 'CG': 'COG', 'CD': 'COD', 'CR': 'CRI', 'CI': 'CIV',
        'HR': 'HRV', 'CU': 'CUB', 'CY': 'CYP', 'CZ': 'CZE', 'DK': 'DNK', 'DJ': 'DJI', 'DM': 'DMA', 'DO': 'DOM',
        'EC': 'ECU', 'EG': 'EGY', 'SV': 'SLV', 'GQ': 'GNQ', 'ER': 'ERI', 'EE': 'EST', 'ET': 'ETH', 'FJ': 'FJI',
        'FI': 'FIN', 'FR': 'FRA', 'GF': 'GUF', 'PF': 'PYF', 'GA': 'GAB', 'GM': 'GMB', 'GE': 'GEO', 'DE': 'DEU',
        'GH': 'GHA', 'GI': 'GIB', 'GR': 'GRC', 'GL': 'GRL', 'GD': 'GRD', 'GP': 'GLP', 'GU': 'GUM', 'GT': 'GTM',
        'GN': 'GIN', 'GW': 'GNB', 'GY': 'GUY', 'HT': 'HTI', 'HN': 'HND', 'HK': 'HKG', 'HU': 'HUN', 'IS': 'ISL',
        'IN': 'IND', 'ID': 'IDN', 'IR': 'IRN', 'IQ': 'IRQ', 'IE': 'IRL', 'IL': 'ISR', 'IT': 'ITA', 'JM': 'JAM',
        'JP': 'JPN', 'JO': 'JOR', 'KZ': 'KAZ', 'KE': 'KEN', 'KI': 'KIR', 'KP': 'PRK', 'KR': 'KOR', 'KW': 'KWT',
        'KG': 'KGZ', 'LA': 'LAO', 'LV': 'LVA', 'LB': 'LBN', 'LS': 'LSO', 'LR': 'LBR', 'LY': 'LBY', 'LI': 'LIE',
        'LT': 'LTU', 'LU': 'LUX', 'MO': 'MAC', 'MK': 'MKD', 'MG': 'MDG', 'MW': 'MWI', 'MY': 'MYS', 'MV': 'MDV',
        'ML': 'MLI', 'MT': 'MLT', 'MH': 'MHL', 'MQ': 'MTQ', 'MR': 'MRT', 'MU': 'MUS', 'YT': 'MYT', 'MX': 'MEX',
        'FM': 'FSM', 'MD': 'MDA', 'MC': 'MCO', 'MN': 'MNG', 'ME': 'MNE', 'MS': 'MSR', 'MA': 'MAR', 'MZ': 'MOZ',
        'MM': 'MMR', 'NA': 'NAM', 'NR': 'NRU', 'NP': 'NPL', 'NL': 'NLD', 'NC': 'NCL', 'NZ': 'NZL', 'NI': 'NIC',
        'NE': 'NER', 'NG': 'NGA', 'NU': 'NIU', 'NF': 'NFK', 'MP': 'MNP', 'NO': 'NOR', 'OM': 'OMN', 'PK': 'PAK',
        'PW': 'PLW', 'PS': 'PSE', 'PA': 'PAN', 'PG': 'PNG', 'PY': 'PRY', 'PE': 'PER', 'PH': 'PHL', 'PN': 'PCN',
        'PL': 'POL', 'PT': 'PRT', 'PR': 'PRI', 'QA': 'QAT', 'RE': 'REU', 'RO': 'ROU', 'RU': 'RUS', 'RW': 'RWA',
        'SH': 'SHN', 'KN': 'KNA', 'LC': 'LCA', 'PM': 'SPM', 'VC': 'VCT', 'WS': 'WSM', 'SM': 'SMR', 'ST': 'STP',
        'SA': 'SAU', 'SN': 'SEN', 'RS': 'SRB', 'SC': 'SYC', 'SL': 'SLE', 'SG': 'SGP', 'SK': 'SVK', 'SI': 'SVN',
        'SB': 'SLB', 'SO': 'SOM', 'ZA': 'ZAF', 'SS': 'SSD', 'ES': 'ESP', 'LK': 'LKA', 'SD': 'SDN', 'SR': 'SUR',
        'SJ': 'SJM', 'SZ': 'SWZ', 'SE': 'SWE', 'CH': 'CHE', 'SY': 'SYR', 'TW': 'TWN', 'TJ': 'TJK', 'TZ': 'TZA',
        'TH': 'THA', 'TL': 'TLS', 'TG': 'TGO', 'TK': 'TKL', 'TO': 'TON', 'TT': 'TTO', 'TN': 'TUN', 'TR': 'TUR',
        'TM': 'TKM', 'TC': 'TCA', 'TV': 'TUV', 'UG': 'UGA', 'UA': 'UKR', 'AE': 'ARE', 'GB': 'GBR', 'US': 'USA',
        'UY': 'URY', 'UZ': 'UZB', 'VU': 'VUT', 'VE': 'VEN', 'VN': 'VNM', 'VG': 'VGB', 'VI': 'VIR', 'WF': 'WLF',
        'EH': 'ESH', 'YE': 'YEM', 'ZM': 'ZMB', 'ZW': 'ZWE'
    }

    # Map country codes to ISO-3
    first_author_country_df["country_iso3"] = first_author_country_df["country_code"].map(ISO2_TO_ISO3)
    
    # Aggregate counts by ISO-3 code
    country_counts = first_author_country_df["country_iso3"].dropna().value_counts().reset_index()
    country_counts.columns = ["country_iso3", "Count"]

    fig_map = px.choropleth(
        country_counts,
        locations="country_iso3",
        locationmode="ISO-3",
        color="Count",
        hover_name="country_iso3",
        color_continuous_scale="Viridis",
        title="First Author Affiliations by Country"
    )
    fig_map.update_layout(
        geo=dict(
            showframe=False,
            showcoastlines=True,
            projection_type='natural earth'
        ),
        margin=dict(l=0, r=0, t=40, b=0)
    )
    st.plotly_chart(fig_map, use_container_width=True)
else:
    st.info("No geographic metadata available for first authors.")

st.markdown("---")

# --- INSTITUTIONAL AFFILIATIONS & HIGH IMPACT PAPERS ---
st.subheader("🔥 Top 5 Most Cited Works")
top_papers = df.sort_values(by="cited_by_count", ascending=False).head(5)[
    ["title", "author", "publication_year", "cited_by_count", "doi"]
].copy()

top_papers.columns = ["Title", "Author", "Year", "Citations", "DOI"]

def make_clickable(val):
    return f'<a href="{val}" target="_blank">{val}</a>' if val and pd.notna(val) else "N/A"

top_papers["DOI"] = top_papers["DOI"].apply(make_clickable)
st.write(top_papers.to_html(escape=False, index=False), unsafe_allow_html=True)

st.markdown("---")

# --- DATA EXPLORER ---
st.subheader("🔍 Data Explorer")
st.dataframe(df[["title", "author", "publication_year", "type", "cited_by_count", "author_count", "primary_topic"]], use_container_width=True)