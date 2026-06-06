---
marp: true
html: true
theme: default
paginate: true
size: 1080x1080
header: ""
footer: ""
---

<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@300;400;500;600;700&family=Playfair+Display:wght@400;700&display=swap');

section {
  font-family: 'Noto Sans TC', sans-serif;
  padding: 50px 60px !important;
  background: linear-gradient(to bottom, #f8f9fa 0%, #ffffff 100%);
  color: #2c3e50;
}

section:first-of-type {
  background: linear-gradient(135deg, #e8f4f8 0%, #d1e7dd 100%);
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
}

h1 {
  font-family: 'Playfair Display', serif;
  font-size: 3.5em !important;
  font-weight: 700 !important;
  margin: 0.3em 0 !important;
  color: #1a365d;
  letter-spacing: -0.5px;
}

h2 {
  font-family: 'Playfair Display', serif;
  font-size: 2.5em !important;
  font-weight: 700 !important;
  margin: 0.5em 0 !important;
  color: #2d3748;
  border-bottom: 3px solid #cbd5e0;
  padding-bottom: 15px;
}

h3 {
  font-size: 1.8em !important;
  font-weight: 600 !important;
  margin: 0.5em 0 !important;
  color: #4a5568;
}

ul, ol {
  margin: 1.2rem 0 !important;
  padding-left: 1.8rem !important;
}

li {
  margin: 0.8rem 0 !important;
  font-size: 1.15em !important;
  line-height: 1.7 !important;
  color: #4a5568;
}

strong {
  font-weight: 600 !important;
  color: #2d3748;
}
</style>

# 財報狗 Podcast 第 500 集
## AI 浪潮與半導體擴產投資建議

---

<style>
section {
  background: linear-gradient(to bottom, #ffffff 0%, #f7fafc 100%);
}

h1 {
  font-size: 2em !important;
}

table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  margin-top: 30px;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 4px 20px rgba(0,0,0,0.08);
  border: 1px solid #e2e8f0;
}

th {
  background: linear-gradient(to bottom, #4a5568 0%, #2d3748 100%);
  color: #ffffff;
  padding: 18px 20px;
  text-align: left;
  font-size: 1.1em;
  font-weight: 600;
  letter-spacing: 0.5px;
}

td {
  padding: 16px 20px;
  background: #ffffff;
  border-bottom: 1px solid #e2e8f0;
  font-size: 1.05em;
  color: #4a5568;
  transition: background-color 0.2s ease;
}

tr:last-child td {
  border-bottom: none;
}

tr:hover td {
  background: #f7fafc;
}

td:first-child {
  font-weight: 600;
  color: #2d3748;
  font-size: 1.1em;
}

.score-elegant {
  display: inline-block;
  padding: 6px 14px;
  border-radius: 20px;
  font-weight: 600;
  font-size: 1em;
  background: linear-gradient(135deg, #48bb78 0%, #38a169 100%);
  color: #ffffff;
  box-shadow: 0 2px 8px rgba(72,187,120,0.25);
}
</style>

# AI 浪潮與半導體擴產投資建議

| 標的 | 情緒 | 分數 | 週期 | 核心投資邏輯 |
| :--- | :--- | :--- | :--- | :--- |
| [2330.TW](#ticker:2330.TW) | 🟢 看多 | <span class="score-elegant">0.85</span> | 長期 | 全球晶圓廠擴產與先進製程領先 |
| [ASML](#ticker:ASML) | 🟢 看多 | <span class="score-elegant">0.75</span> | 中期 | 大晶圓廠時代帶動微影設備需求 |
| [6759.T](#ticker:6759.T) | 🟢 看多 | <span class="score-elegant">0.80</span> | 中期 | AI 伺服器推升 MLCC 密度與價值 |
| [GOOGL](#ticker:GOOGL) | 🟢 看多 | <span class="score-elegant">0.70</span> | 中期 | AI 服務生態系中的「過路費」優勢 |
| [3576.TW](#ticker:3576.TW) | 🟢 看多 | <span class="score-elegant">0.65</span> | 短期 | 美國資料中心電力短缺帶動動能 |

---

<style>
section {
  background: linear-gradient(to bottom, #ffffff 0%, #f7fafc 100%);
}

.ticker-dashboard {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 40px;
  height: 100%;
}

.sidebar {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.score-panel {
  background: linear-gradient(135deg, #ffffff 0%, #f7fafc 100%);
  border-radius: 16px;
  padding: 40px 30px;
  border: 2px solid #e2e8f0;
  text-align: center;
  box-shadow: 0 4px 12px rgba(0,0,0,0.05);
}

.score-circle-large {
  width: 200px;
  height: 200px;
  margin: 0 auto 30px;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.score-ring {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  border: 12px solid #e2e8f0;
  position: absolute;
  top: 0;
  left: 0;
}

.score-ring-85 {
  border-top-color: #48bb78;
  border-right-color: #48bb78;
  border-bottom-color: transparent;
  border-left-color: transparent;
  transform: rotate(54deg);
}

.score-ring-75 {
  border-top-color: #48bb78;
  border-right-color: #48bb78;
  border-bottom-color: transparent;
  border-left-color: transparent;
  transform: rotate(0deg);
}

.score-ring-80 {
  border-top-color: #48bb78;
  border-right-color: #48bb78;
  border-bottom-color: transparent;
  border-left-color: transparent;
  transform: rotate(72deg);
}

.score-ring-70 {
  border-top-color: #48bb78;
  border-right-color: #48bb78;
  border-bottom-color: transparent;
  border-left-color: transparent;
  transform: rotate(-36deg);
}

.score-ring-65 {
  border-top-color: #48bb78;
  border-right-color: #48bb78;
  border-bottom-color: transparent;
  border-left-color: transparent;
  transform: rotate(-54deg);
}

.score-inner {
  width: 160px;
  height: 160px;
  border-radius: 50%;
  background: linear-gradient(135deg, #f0fff4 0%, #e6fffa 100%);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  z-index: 1;
  position: relative;
  border: 2px solid #cbd5e0;
}

.score-main {
  font-size: 3.5em;
  font-weight: 300;
  color: #48bb78;
  line-height: 1;
  font-family: 'Playfair Display', serif;
}

.score-label {
  font-size: 0.9em;
  color: #718096;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-top: 8px;
  font-weight: 500;
}

.sentiment-badge {
  display: inline-block;
  padding: 12px 24px;
  background: linear-gradient(135deg, #48bb78 0%, #38a169 100%);
  color: #ffffff;
  border-radius: 20px;
  font-weight: 600;
  font-size: 1.1em;
  margin: 15px 0;
  box-shadow: 0 2px 8px rgba(72,187,120,0.25);
}

.timeframe-badge {
  display: inline-block;
  padding: 10px 20px;
  background: linear-gradient(135deg, #edf2f7 0%, #e2e8f0 100%);
  color: #4a5568;
  border-radius: 16px;
  font-weight: 500;
  font-size: 0.95em;
  border: 1px solid #cbd5e0;
  margin-top: 10px;
}
/*# here*/
.content-panel { 
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.bluf-card {
  background: linear-gradient(135deg, #f0fff4 0%, #e6fffa 100%);
  border-radius: 12px;
  padding: 3px;
  border-left: 4px solid #48bb78;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  margin-bottom: 1px;
}

.bluf-header {
  font-size: 0.7em;
  text-transform: uppercase;
  letter-spacing: 1.5px;
  color: #48bb78;
  font-weight: 600;
  margin-bottom: 2px;
}

.bluf-text {
  font-size: 0.55em;
  line-height: 2;
  color: #2d3748;
  font-weight: 400;
}

.reasons-grid {
  display: grid;
  gap: 3px;
}

.reason-card {
  background: #ffffff;
  border-radius: 1px;
  padding: 2px 3px;
  border-left: 3px solid #48bb78;
  box-shadow: 0 2px 6px rgba(0,0,0,0.04);
  transition: all 0.2s ease;
}

.reason-card:hover {
  transform: translateX(3px);
  box-shadow: 0 1px 1px rgba(0,0,0,0.08);
  border-left-color: #38a169;
}

.reason-title {
  font-size: 0.7em;
  font-weight: 600;
  color: #2d3748;
  margin-bottom: 0.1px;
  display: flex;
  align-items: center;
  gap: 0.1px;
}

.reason-desc {
  font-size: 0.55em;
  color: #4a5568;
  line-height: 1.8;
  margin-top: 0;
}

.risks-grid {
  display: grid;
  gap: 2px;
}

.risk-card {
  background: #ffffff;
  border-radius: 1px;
  padding: 2px 3px;
  box-shadow: 0 2px 6px rgba(0,0,0,0.04);
  transition: all 0.2s ease;
}

.risk-card:hover {
  transform: translateX(3px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}

.risk-medium {
  border-left: 3px solid #ed8936;
  background: linear-gradient(to right, #fffaf0 0%, #ffffff 100%);
}

.risk-high {
  border-left: 3px solid #fc8181;
  background: linear-gradient(to right, #fff5f5 0%, #ffffff 100%);
}

.risk-low {
  border-left: 3px solid #f6e05e;
  background: linear-gradient(to right, #fffbeb 0%, #ffffff 100%);
}

.risk-title {
  font-size: 0.7em;
  font-weight: 600;
  margin-bottom: 0.1px;
  display: flex;
  align-items: center;
  gap: 0.1px;
}

.risk-medium .risk-title {
  color: #c05621;
}

.risk-high .risk-title {
  color: #c53030;
}

.risk-low .risk-title {
  color: #744210;
}

.risk-desc {
  font-size: 0.55em;
  color: #4a5568;
  line-height: 1.8;
  margin-top: 0;
}

.section-header {
  font-size: 0.7em;
  font-weight: 600;
  color: #2d3748;
  margin-bottom: 0.1px;
  margin-top: 0.1px;
  padding-bottom: 0.1px;
  border-bottom: 0.1px solid #e2e8f0;
}
</style>

# [台積電](#ticker:2330.TW) | 2330.TW

<div class="ticker-dashboard">
  <div class="sidebar">
    <div class="score-panel">
      <div class="score-circle-large">
        <div class="score-ring score-ring-85"></div>
        <div class="score-inner">
          <div class="score-main">0.85</div>
          <div class="score-label">Score</div>
        </div>
      </div>
      <div class="sentiment-badge">🟢 看多</div>
      <div class="timeframe-badge">時間維度：長期</div>
    </div>
  </div>
  <div class="content-panel">
    <div class="bluf-card">
      <div class="bluf-header">核心邏輯 (BLUF)</div>
      <div class="bluf-text">全球晶圓廠大擴產潮下，台積電憑藉 2nm/3nm 先進製程的絕對領導地位與 AI 需求，維持強勁增長。</div>
    </div>
    <div class="section-header">投資理由</div>
    <div class="reasons-grid">
      <div class="reason-card">
        <div class="reason-title">📈 亞利桑那大擴產傳聞</div>
        <div class="reason-desc">傳聞將建立 5-10 座晶圓廠以滿足地緣政治與供應鏈需求。 [#time:914381](#time:914381)</div>
      </div>
      <div class="reason-card">
        <div class="reason-title">🎯 先進製程領導地位</div>
        <div class="reason-desc">2nm 與 3nm 在效能與良率上顯著領先對手。 [#time:1455202](#time:1455202)</div>
      </div>
      <div class="reason-card">
        <div class="reason-title">💡 AI 新創需求紅利</div>
        <div class="reason-desc">AI 公司對 2nm 興趣濃厚，儘管成本高昂仍積極預訂。 [#time:1567363](#time:1567363)</div>
      </div>
    </div>
    <div class="section-header">風險提示</div>
    <div class="risks-grid">
      <div class="risk-card risk-medium">
        <div class="risk-title">⚠️ 海外管理衝突 (中)</div>
        <div class="risk-desc">亞利桑那廠文化與管理挑戰 [#time:1271282](#time:1271282)</div>
      </div>
      <div class="risk-card risk-medium">
        <div class="risk-title">⚠️ 地緣政治關稅 (中)</div>
        <div class="risk-desc">高階 GPU 進口關稅可能衝擊供應鏈 [#time:1110561](#time:1110561)</div>
      </div>
    </div>
  </div>
</div>

---

<style>
.score-ring {
  border-color: #e2e8f0;
}
</style>

# [ASML](#ticker:ASML) | ASML

<div class="ticker-dashboard">
  <div class="sidebar">
    <div class="score-panel">
      <div class="score-circle-large">
        <div class="score-ring score-ring-75"></div>
        <div class="score-inner">
          <div class="score-main">0.75</div>
          <div class="score-label">Score</div>
        </div>
      </div>
      <div class="sentiment-badge">🟢 看多</div>
      <div class="timeframe-badge">時間維度：中期</div>
    </div>
  </div>
  <div class="content-panel">
    <div class="bluf-card">
      <div class="bluf-header">核心邏輯 (BLUF)</div>
      <div class="bluf-text">身為「大晶圓廠時代」受益者，全球半導體產能擴張直接驅動對高階微影設備的強勁需求。</div>
    </div>
    <div class="section-header">投資理由</div>
    <div class="reasons-grid">
      <div class="reason-card">
        <div class="reason-title">📈 全球晶圓廠大擴張</div>
        <div class="reason-desc">全球擴產浪潮處於 20 年高點，新加坡、日本、德國均在建廠。 [#time:1141001](#time:1141001)</div>
      </div>
    </div>
    <div class="section-header">風險提示</div>
    <div class="risks-grid">
      <div class="risk-card risk-high">
        <div class="risk-title">🔴 中國出口限制 (高)</div>
        <div class="risk-desc">對中高階設備出口禁令影響顯著營收組成。 [#time:1048561](#time:1048561)</div>
      </div>
    </div>
  </div>
</div>

---

# [太誘](#ticker:6759.T) | 6759.T

<div class="ticker-dashboard">
  <div class="sidebar">
    <div class="score-panel">
      <div class="score-circle-large">
        <div class="score-ring score-ring-80"></div>
        <div class="score-inner">
          <div class="score-main">0.80</div>
          <div class="score-label">Score</div>
        </div>
      </div>
      <div class="sentiment-badge">🟢 看多</div>
      <div class="timeframe-badge">時間維度：中期</div>
    </div>
  </div>
  <div class="content-panel">
    <div class="bluf-card">
      <div class="bluf-header">核心邏輯 (BLUF)</div>
      <div class="bluf-text">AI 伺服器需求預計將帶動 MLCC 需求至 2030 年成長 4.3 倍，高階被動元件龍頭直接受惠。</div>
    </div>
    <div class="section-header">投資理由</div>
    <div class="reasons-grid">
      <div class="reason-card">
        <div class="reason-title">📈 AI 伺服器 MLCC 密度提升</div>
        <div class="reason-desc">每台機架 MLCC 使用量大幅增加（達 45 萬顆），帶動價量齊揚。 [#time:1745223](#time:1745223)</div>
      </div>
      <div class="reason-card">
        <div class="reason-title">⚡ HVDC 架構升級</div>
        <div class="reason-desc">資料中心改採高壓直流電架構，增加高壓 MLCC 元件使用。 [#time:1816164](#time:1816164)</div>
      </div>
    </div>
    <div class="section-header">風險提示</div>
    <div class="risks-grid">
      <div class="risk-card risk-low">
        <div class="risk-title">🟡 原物料價格波動 (低)</div>
        <div class="risk-desc">銀、銅等導電漿原料成本上升可能壓縮毛利。 [#time:2226705](#time:2226705)</div>
      </div>
    </div>
  </div>
</div>

---

# [Google](#ticker:GOOGL) | GOOGL

<div class="ticker-dashboard">
  <div class="sidebar">
    <div class="score-panel">
      <div class="score-circle-large">
        <div class="score-ring score-ring-70"></div>
        <div class="score-inner">
          <div class="score-main">0.70</div>
          <div class="score-label">Score</div>
        </div>
      </div>
      <div class="sentiment-badge">🟢 看多</div>
      <div class="timeframe-badge">時間維度：中期</div>
    </div>
  </div>
  <div class="content-panel">
    <div class="bluf-card">
      <div class="bluf-header">核心邏輯 (BLUF)</div>
      <div class="bluf-text">Google 定位為 AI 服務的「過路費之王」，憑藉生態系優勢，無論硬體或軟體夥伴皆須支付其運算與搜尋存取費用。</div>
    </div>
    <div class="section-header">投資理由</div>
    <div class="reasons-grid">
      <div class="reason-card">
        <div class="reason-title">💰 生態系規費支配力</div>
        <div class="reason-desc">在 AI 生態系中佔據策略性地位，形成實質上的「Google 稅」。 [#time:1632943](#time:1632943)</div>
      </div>
    </div>
  </div>
</div>

---

# [聯合再生](#ticker:3576.TW) | 3576.TW

<div class="ticker-dashboard">
  <div class="sidebar">
    <div class="score-panel">
      <div class="score-circle-large">
        <div class="score-ring score-ring-65"></div>
        <div class="score-inner">
          <div class="score-main">0.65</div>
          <div class="score-label">Score</div>
        </div>
      </div>
      <div class="sentiment-badge">🟢 看多</div>
      <div class="timeframe-badge">時間維度：短期</div>
    </div>
  </div>
  <div class="content-panel">
    <div class="bluf-card">
      <div class="bluf-header">核心邏輯 (BLUF)</div>
      <div class="bluf-text">受惠於美國 AI 資料中心極度缺電，帶動再生能源與相關電力基礎設施投資，形成短期股價動能。</div>
    </div>
    <div class="section-header">投資理由</div>
    <div class="reasons-grid">
      <div class="reason-card">
        <div class="reason-title">⚡ 美國電力短缺紅利</div>
        <div class="reason-desc">AI 設施引發的電力不足驅動微電網與再生能源投資回溫。 [#time:2514726](#time:2514726)</div>
      </div>
    </div>
  </div>
</div>

---
