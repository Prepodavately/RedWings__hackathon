"""Shared visual language for a presentation-ready dashboard."""
import plotly.io as pio
import plotly.graph_objects as go
import streamlit as st

NAVY='#12233F'
RED='#D82F4C'
BLUE='#247AAB'


def apply_style():
    pio.templates['rw']=go.layout.Template(layout=dict(
        font=dict(family='Arial, sans-serif',size=13,color=NAVY),
        paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='#F6F8FC',
        colorway=[BLUE,RED,'#16A085','#8091AD'],
        margin=dict(l=20,r=25,t=35,b=35),
        xaxis=dict(showgrid=False,zeroline=False,title_font_size=12),
        yaxis=dict(gridcolor='#E4EAF2',zeroline=False,title_font_size=12),
        legend=dict(orientation='h',y=1.12,x=0,title_text=''),
        hoverlabel=dict(bgcolor=NAVY,font_color='white',font_size=13),
    ))
    pio.templates.default='plotly_white+rw'
    st.markdown('''<style>
    .stApp{background:#F5F7FB;color:#12233F}
    .block-container{max-width:1480px;padding:2.2rem 2.5rem 3rem}
    h1,h2,h3{color:#12233F;letter-spacing:-.035em}
    h1{font-size:2.5rem!important;font-weight:800!important}
    h3{font-size:1.35rem!important}
    [data-testid="stSidebar"]{background:#FFF;border-right:1px solid #E2E8F1}
    [data-testid="stMetric"]{background:white;border:1px solid #E0E6F0;border-radius:14px;padding:18px!important;box-shadow:0 4px 16px #12233F05}
    [data-testid="stMetricValue"]{font-size:2rem!important;letter-spacing:-.04em}
    [data-testid="stMetricLabel"]{color:#61708A;font-size:.85rem}
    button[data-baseweb="tab"]{font-size:14px;font-weight:650;padding:12px 20px}
    [data-baseweb="tab-list"]{gap:5px;background:white;border-radius:12px;padding:5px}
    [data-testid="stPlotlyChart"]{background:white;border:1px solid #E3E9F1;border-radius:16px;padding:10px}
    [data-testid="stDataFrame"]{border-radius:12px;overflow:hidden}
    .rw-hero{background:linear-gradient(115deg,#11213C,#213B61);border-radius:20px;padding:28px 34px;margin-bottom:22px;color:white;position:relative;overflow:hidden}
    .rw-hero:after{content:'';position:absolute;width:200px;height:200px;border:35px solid #FFFFFF08;transform:rotate(35deg);right:20px;top:-100px}
    .rw-eyebrow{color:#A9C0DD;font-size:11px;letter-spacing:.19em;font-weight:700}
    .rw-hero h1{color:white!important;margin:8px 0 4px!important;padding:0!important}
    .rw-hero p{color:#C4D2E4;font-size:14px;margin:8px 0 0}
    .rw-badge{display:inline-block;border:1px solid #FFFFFF35;padding:5px 10px;border-radius:30px;margin-top:18px;font-size:11px;color:#DCE7F7}
    .rw-section{font-size:11px;letter-spacing:.14em;color:#77869B;text-transform:uppercase;margin:18px 0 8px}
    .rw-strategy{border-left:4px solid #247AAB;padding:12px 16px;background:#EAF4FA;border-radius:0 10px 10px 0;font-size:18px;font-weight:700;margin:12px 0}
    .rw-strategy.hub{border-color:#D82F4C;background:#FCEEF1}
    @media(max-width:700px){.block-container{padding:1rem}.rw-hero{padding:22px}h1{font-size:1.8rem!important}}
    </style>''',unsafe_allow_html=True)


def hero():
    st.markdown('''<div class="rw-hero"><div class="rw-eyebrow">RED WINGS / NETWORK STRATEGY LAB</div><h1>Следующий маршрут — обоснованный выбор.</h1><p>Региональный хаб или прямые рейсы: спрос, экономика и устойчивость решения на одном экране.</p><span class="rw-badge">12 городов · 2 стратегии · горизонт 2028</span></div>''',unsafe_allow_html=True)
