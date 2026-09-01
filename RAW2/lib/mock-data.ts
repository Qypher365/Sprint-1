// ---------------------------------------------------------------------------
// MOCK DATA SOURCE
// ---------------------------------------------------------------------------
// This file is the ONLY place that holds demo values for the dashboard.
// Every number, string, and status below is synthetic/demo data used to
// prototype the UI. Nothing here is live or real financial data.
//
// When a real backend is available, replace `getStockData(symbol)` with a
// fetch to the API. The rest of the app consumes the same `StockData` shape
// via props, so no UI component needs to change.
// ---------------------------------------------------------------------------

export type Signal = "BULLISH" | "BEARISH" | "NEUTRAL"
export type AgentStatus = "idle" | "processing" | "complete" | "error"
export type RiskProfile = "conservative" | "aggressive"

export interface AgentTimelineStep {
  label: string
  value: string
}

export interface Agent {
  id: string
  name: string
  role: string
  status: AgentStatus
  signal: Signal | null
  confidence: number | null
  summary: string
  hoverDetail: string
  errorMessage?: string
  metrics?: Record<string, string>
  timeline?: AgentTimelineStep[]
}

export interface Citation {
  title: string
  source: string
  label: string
  summary: string
}

export interface Synthesis {
  signal: Signal
  confidence: number
  summary: string
  reasons: string[]
  riskImpact: Record<RiskProfile, string>
  conflicting: boolean
}

export interface SessionMetrics {
  latencyMs: number
  riskConcentrationPct: number
  accuracyPct: number
}

export interface StockData {
  symbol: string
  name: string
  price: number
  change: number
  changePercent: number
  lastUpdated: string
  sparkline: number[]
  agents: Agent[]
  synthesis: Synthesis | null
  citations: Citation[]
  metrics: SessionMetrics
  empty?: boolean
}

// ---------------------------------------------------------------------------
// Assets available in the Asset Selector.
// Each demonstrates a distinct dashboard state required by the spec.
// ---------------------------------------------------------------------------

export const ASSETS = [
  { symbol: "RELIANCE", name: "Reliance Industries Ltd." },
  { symbol: "TCS", name: "Tata Consultancy Services" },
  { symbol: "INFY", name: "Infosys Ltd." },
  { symbol: "ITC", name: "ITC Ltd." },
] as const

export type AssetSymbol = (typeof ASSETS)[number]["symbol"]

const RELIANCE_SPARKLINE = [1408, 1412, 1401, 1419, 1424, 1431, 1427, 1438, 1444, 1450]
const TCS_SPARKLINE = [3810, 3822, 3795, 3801, 3788, 3812, 3805, 3798, 3790, 3796]
const INFY_SPARKLINE = [1512, 1519, 1508, 1522, 1515, 1498, 1503, 1497, 1489, 1494]
const ITC_SPARKLINE = [438, 439, 437, 438, 438, 439, 438, 437, 438, 438]

const MOCK_DB: Record<AssetSymbol, StockData> = {
  // ---------------------------------------------------------------------
  // RELIANCE — "happy path": agents agree, clean bullish synthesis.
  // ---------------------------------------------------------------------
  RELIANCE: {
    symbol: "RELIANCE",
    name: "Reliance Industries Ltd.",
    price: 1450,
    change: 18.4,
    changePercent: 1.28,
    lastUpdated: "2 seconds ago",
    sparkline: RELIANCE_SPARKLINE,
    agents: [
      {
        id: "technical",
        name: "Technical Agent",
        role: "Price action & momentum",
        status: "complete",
        signal: "BULLISH",
        confidence: 86,
        summary: "Positive momentum supported by above-average volume.",
        hoverDetail: "5-day trend classified bullish across two consecutive sessions.",
        metrics: { Momentum: "+2.4%", "Volume Δ": "+18%" },
        timeline: [
          { label: "Price momentum", value: "+2.4% over 5 sessions" },
          { label: "Volume change", value: "+18% vs. 20-day average" },
          { label: "Trend classification", value: "Bullish" },
          { label: "Confidence", value: "86%" },
        ],
      },
      {
        id: "sentiment",
        name: "Sentiment Agent",
        role: "News & social signal",
        status: "complete",
        signal: "NEUTRAL",
        confidence: 64,
        summary: "Mixed but moderately positive market sentiment.",
        hoverDetail: "Analyst commentary skews positive; retail chatter is neutral.",
        metrics: { "News tone": "+0.3", "Social volume": "Moderate" },
        timeline: [
          { label: "News sentiment score", value: "+0.3 (moderately positive)" },
          { label: "Social mention volume", value: "Moderate, steady" },
          { label: "Analyst tone", value: "Constructive" },
          { label: "Confidence", value: "64%" },
        ],
      },
      {
        id: "fundamental",
        name: "Fundamental Agent",
        role: "Financials & filings",
        status: "complete",
        signal: "BULLISH",
        confidence: 78,
        summary: "Positive financial indicators from latest filing.",
        hoverDetail: "Operating margin expanded 140bps year-over-year.",
        metrics: { "Margin Δ": "+140bps", "Debt/Equity": "0.38x" },
        timeline: [
          { label: "Operating margin", value: "+140bps YoY" },
          { label: "Debt / equity", value: "0.38x (improved)" },
          { label: "Revenue growth", value: "+9.1% YoY" },
          { label: "Confidence", value: "78%" },
        ],
      },
    ],
    synthesis: {
      signal: "BULLISH",
      confidence: 82,
      summary:
        "Overall signals are moderately bullish, driven by strong technical momentum and healthy fundamentals.",
      reasons: [
        "Positive price momentum",
        "Above-average volume",
        "Moderately positive sentiment",
        "Improving operating margin",
      ],
      riskImpact: {
        conservative: "Moderate exposure may be preferable given continued upside confirmation.",
        aggressive: "Higher-risk exposure may be considered while momentum persists.",
      },
      conflicting: false,
    },
    citations: [
      {
        title: "Q1 Financial Filing",
        source: "SEBI",
        label: "Q1 FY27",
        summary: "Quarterly regulatory filing covering revenue, margins, and segment performance.",
      },
      {
        title: "Earnings Call Transcript",
        source: "Company IR",
        label: "Earnings Report",
        summary: "Management commentary on capex plans and forward guidance.",
      },
      {
        title: "Intraday Trade Tape",
        source: "NSE",
        label: "Market Data",
        summary: "Price and volume data aggregated from exchange feed.",
      },
    ],
    metrics: { latencyMs: 420, riskConcentrationPct: 34, accuracyPct: 81 },
  },

  // ---------------------------------------------------------------------
  // TCS — "conflicting agents": Technical bullish, Sentiment bearish,
  // Fundamental neutral.
  // ---------------------------------------------------------------------
  TCS: {
    symbol: "TCS",
    name: "Tata Consultancy Services",
    price: 3796,
    change: -14.2,
    changePercent: -0.37,
    lastUpdated: "4 seconds ago",
    sparkline: TCS_SPARKLINE,
    agents: [
      {
        id: "technical",
        name: "Technical Agent",
        role: "Price action & momentum",
        status: "complete",
        signal: "BULLISH",
        confidence: 71,
        summary: "Short-term breakout above 20-day moving average.",
        hoverDetail: "Momentum indicators turned positive after a two-week consolidation.",
        metrics: { Momentum: "+1.1%", "Volume Δ": "+6%" },
        timeline: [
          { label: "Price momentum", value: "+1.1% over 3 sessions" },
          { label: "Volume change", value: "+6% vs. 20-day average" },
          { label: "Trend classification", value: "Bullish breakout" },
          { label: "Confidence", value: "71%" },
        ],
      },
      {
        id: "sentiment",
        name: "Sentiment Agent",
        role: "News & social signal",
        status: "complete",
        signal: "BEARISH",
        confidence: 68,
        summary: "Negative sentiment following client budget cut headlines.",
        hoverDetail: "Coverage of a major client's IT spend reduction is dominating tone.",
        metrics: { "News tone": "-0.4", "Social volume": "Elevated" },
        timeline: [
          { label: "News sentiment score", value: "-0.4 (negative)" },
          { label: "Headline driver", value: "Client budget-cut coverage" },
          { label: "Social mention volume", value: "Elevated, negative-skewed" },
          { label: "Confidence", value: "68%" },
        ],
      },
      {
        id: "fundamental",
        name: "Fundamental Agent",
        role: "Financials & filings",
        status: "complete",
        signal: "NEUTRAL",
        confidence: 58,
        summary: "Stable financials with no significant change this quarter.",
        hoverDetail: "Margins held flat; deal pipeline commentary was non-committal.",
        metrics: { "Margin Δ": "+10bps", "Debt/Equity": "0.21x" },
        timeline: [
          { label: "Operating margin", value: "+10bps YoY (flat)" },
          { label: "Debt / equity", value: "0.21x (stable)" },
          { label: "Deal pipeline commentary", value: "Non-committal" },
          { label: "Confidence", value: "58%" },
        ],
      },
    ],
    synthesis: {
      signal: "NEUTRAL",
      confidence: 54,
      summary:
        "Signals conflict: technical strength is offset by negative sentiment, and the synthesis is being made with conflicting inputs.",
      reasons: [
        "Technical breakout vs. negative headline sentiment",
        "Fundamentals unchanged this quarter",
        "Elevated but negative-skewed social volume",
        "No clear directional consensus across agents",
      ],
      riskImpact: {
        conservative: "Reduced conviction suggests waiting for signal alignment before adding exposure.",
        aggressive: "Volatility may present tactical entries, but position sizing should stay conservative.",
      },
      conflicting: true,
    },
    citations: [
      {
        title: "Client Budget Disclosure",
        source: "Reuters",
        label: "News Wire",
        summary: "Third-party reporting on a major client's technology spending plans.",
      },
      {
        title: "Q1 Financial Filing",
        source: "SEBI",
        label: "Q1 FY27",
        summary: "Quarterly regulatory filing covering revenue, margins, and segment performance.",
      },
      {
        title: "Intraday Trade Tape",
        source: "NSE",
        label: "Market Data",
        summary: "Price and volume data aggregated from exchange feed.",
      },
    ],
    metrics: { latencyMs: 486, riskConcentrationPct: 41, accuracyPct: 74 },
  },

  // ---------------------------------------------------------------------
  // INFY — "agent failure / unavailable": Sentiment Agent is down.
  // ---------------------------------------------------------------------
  INFY: {
    symbol: "INFY",
    name: "Infosys Ltd.",
    price: 1494,
    change: -8.6,
    changePercent: -0.57,
    lastUpdated: "9 seconds ago",
    sparkline: INFY_SPARKLINE,
    agents: [
      {
        id: "technical",
        name: "Technical Agent",
        role: "Price action & momentum",
        status: "complete",
        signal: "BEARISH",
        confidence: 73,
        summary: "Momentum weakening after break below support.",
        hoverDetail: "Price closed below the 50-day moving average for the second session.",
        metrics: { Momentum: "-1.8%", "Volume Δ": "+11%" },
        timeline: [
          { label: "Price momentum", value: "-1.8% over 4 sessions" },
          { label: "Volume change", value: "+11% vs. 20-day average" },
          { label: "Trend classification", value: "Bearish" },
          { label: "Confidence", value: "73%" },
        ],
      },
      {
        id: "sentiment",
        name: "Sentiment Agent",
        role: "News & social signal",
        status: "error",
        signal: null,
        confidence: null,
        summary: "Agent unavailable — news feed connection timed out.",
        hoverDetail: "Retrying automatically; synthesis will exclude this agent until it recovers.",
        errorMessage: "News feed provider timeout after 3 retries. Last successful sync: 41 minutes ago.",
      },
      {
        id: "fundamental",
        name: "Fundamental Agent",
        role: "Financials & filings",
        status: "complete",
        signal: "NEUTRAL",
        confidence: 61,
        summary: "Guidance held steady; margin pressure from wage hikes.",
        hoverDetail: "Management reiterated full-year guidance without revision.",
        metrics: { "Margin Δ": "-60bps", "Debt/Equity": "0.09x" },
        timeline: [
          { label: "Operating margin", value: "-60bps YoY (wage hike impact)" },
          { label: "Debt / equity", value: "0.09x (very low)" },
          { label: "Guidance", value: "Reiterated, unchanged" },
          { label: "Confidence", value: "61%" },
        ],
      },
    ],
    synthesis: {
      signal: "BEARISH",
      confidence: 58,
      summary:
        "Signal generated with reduced coverage: the Sentiment Agent is currently unavailable, so synthesis relies on technical and fundamental inputs only.",
      reasons: [
        "Break below key technical support",
        "Margin pressure from wage-related costs",
        "Sentiment Agent unavailable — excluded from this synthesis",
        "Unchanged full-year guidance",
      ],
      riskImpact: {
        conservative: "Consider trimming exposure until full agent coverage is restored.",
        aggressive: "Reduced signal coverage warrants tighter stops on any new positions.",
      },
      conflicting: false,
    },
    citations: [
      {
        title: "Q1 Financial Filing",
        source: "SEBI",
        label: "Q1 FY27",
        summary: "Quarterly regulatory filing covering revenue, margins, and segment performance.",
      },
      {
        title: "Intraday Trade Tape",
        source: "NSE",
        label: "Market Data",
        summary: "Price and volume data aggregated from exchange feed.",
      },
    ],
    metrics: { latencyMs: 512, riskConcentrationPct: 29, accuracyPct: 69 },
  },

  // ---------------------------------------------------------------------
  // ITC — "empty state": not enough data has been collected yet.
  // ---------------------------------------------------------------------
  ITC: {
    symbol: "ITC",
    name: "ITC Ltd.",
    price: 438,
    change: 0.4,
    changePercent: 0.09,
    lastUpdated: "just now",
    sparkline: ITC_SPARKLINE,
    agents: [
      {
        id: "technical",
        name: "Technical Agent",
        role: "Price action & momentum",
        status: "idle",
        signal: null,
        confidence: null,
        summary: "Awaiting sufficient price history for this session.",
        hoverDetail: "Coverage for this ticker was added recently; backfill is in progress.",
      },
      {
        id: "sentiment",
        name: "Sentiment Agent",
        role: "News & social signal",
        status: "idle",
        signal: null,
        confidence: null,
        summary: "No qualifying news volume in the last 24 hours.",
        hoverDetail: "Sentiment requires a minimum mention threshold to report confidence.",
      },
      {
        id: "fundamental",
        name: "Fundamental Agent",
        role: "Financials & filings",
        status: "idle",
        signal: null,
        confidence: null,
        summary: "No new filings since last synthesis run.",
        hoverDetail: "Next scheduled filing review follows the upcoming quarterly release.",
      },
    ],
    synthesis: null,
    citations: [],
    metrics: { latencyMs: 0, riskConcentrationPct: 0, accuracyPct: 0 },
    empty: true,
  },
}

export function getStockData(symbol: AssetSymbol): StockData {
  return MOCK_DB[symbol]
}
