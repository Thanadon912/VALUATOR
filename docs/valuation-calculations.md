# Valuation Calculation Source of Truth

เอกสารนี้เป็นข้อกำหนดสูตรที่ระบบต้องใช้จริง ห้ามปรับสมมติฐานเพื่อบังคับให้ fair value เท่าราคาตลาด และห้ามสร้างค่าทดแทนเมื่อข้อมูลที่จำเป็นไม่มี

## 1. Data, provenance, and share basis

- Provider facts, provider estimates, user assumptions และค่าที่ระบบคำนวณต้องมีสถานะแยกจากกัน
- ค่าจาก provider ต้องเก็บแหล่งข้อมูลและเวลาเมื่อมี
- DCF ต่อหุ้นใช้ current point-in-time shares outstanding เป็นหลัก; weighted-average diluted shares แสดงเป็นข้อมูลประกอบและใช้เป็น fallback เท่านั้น
- ข้อมูล consensus ใช้เฉพาะแถวที่มี Revenue และ EBIT แบบ Low/Avg/High ครบและเรียง `Low <= Avg <= High`
- เมื่อ consensus ที่ valid มีน้อยกว่า 2 ปี ให้ใช้ filing-derived forecast พร้อม warning ห้ามเติม consensus เอง

$$NOWC=(Current\ Assets-Cash)-(Current\ Liabilities-Short\ Term\ Debt)$$

$$\Delta NWC=NOWC_t-NOWC_{t-1}$$

$$CAGR=(Ending/Beginning)^{1/n}-1$$

## 2. Cost of capital

$$K_e=R_f+\beta\times MRP+CRP$$

โดย `MRP = 5.5%`; `CRP = 0` เมื่อไม่มี country premium ที่เกี่ยวข้อง

$$K_d=Interest\ Expense/Total\ Debt$$

$$WACC=(E/V)K_e+(D/V)K_d(1-T)$$

WACC ปัจจุบันใช้ market-value capital structure ที่มีแหล่งข้อมูล ส่วน terminal WACC ให้ beta ค่อย ๆ เข้าหา `1.0` และคง debt weights ที่มีแหล่งข้อมูลไว้ ต้องมี `terminal WACC > g`; minimum spread คือ `0.5%` เมื่อจำเป็น ไม่มี hard cap 10%

## 3. The five valuation engines

1. Asset-Based: `NAV = Total Assets - Total Liabilities`; `Tangible NAV = NAV - Goodwill - Intangibles`
2. Adaptive DCF: Standard Driver-Based, Capitalized R&D, Regulatory FCFE หรือ Normalized Median ตาม sector/SIC
3. DDM: `V0 = D0(1+g)/(Ke-g)` เมื่อ dividend และ `Ke > g` valid
4. Relative: ใช้ median peer `P/E`, `P/B`, `EV/EBITDA`; EV multiple ต้องทำ equity bridge ก่อนหารหุ้น
5. Residual Income: `V0 = BV0 + PV(Residual Income) + PV(Terminal Value)`

Monte Carlo และ Reverse DCF เป็น analytical layers ของ Adaptive DCF ไม่ใช่ valuation engines เพิ่มเติม

## 4. Growth Multi-Stage FCFF DCF v2

โมเดลนี้ใช้กับ growth/technology company และมี horizon ปกติ 15 ปี

### 4.1 Forecast stages

- Stage 1: ใช้ analyst consensus Revenue และ EBIT Low/Avg/High สูงสุด 5 ปี เมื่อมีข้อมูล valid
- Filing fallback: ใช้ sourced historical growth/margin เมื่อ consensus ไม่พอ พร้อม `estimated_with_warning`
- Transition: ใช้ smoothstep เพื่อ fade revenue growth, EBIT margin และ WACC ไปสู่ mature state โดยไม่กระโดดทันที

Terminal (mature) EBIT margin ต้องเลือกตามลำดับนี้ และต้องเปิดเผย `terminal_margin_basis` เสมอ:

1. เมื่อมี consensus valid ตาม §1 **และผ่าน plausibility check** ให้ใช้ EBIT margin ของปี consensus สุดท้าย บวก R&D adjustment ตาม §4.3
2. เมื่อไม่มี consensus หรือ consensus ไม่ผ่าน plausibility check ให้ใช้ current sourced operating margin (base-year EBIT margin) บวก R&D adjustment

ห้ามให้มัธยฐานย้อนหลังหลายปี override consensus ที่ valid และห้ามใช้มัธยฐานย้อนหลังเป็น fallback เพราะจะตรึง terminal profitability ของธุรกิจที่ margin กำลังขยายไว้ที่ค่าเฉลี่ยอดีต และมัธยฐานอาจรวมปีวิกฤต/ขาดทุนที่ไม่ใช่ steady state (พิสูจน์แล้วจากกรณีจริง: มัธยฐาน 5 ปีของ AMZN รวมปี 2022 ที่ margin ตกเหลือ 2.4% ทำให้ terminal margin ต่ำกว่าที่ควรมาก) current sourced margin (ปีล่าสุดจริง) เป็น anchor ที่ปลอดภัยกว่าเมื่อไม่มีสัญญาณ forward-looking ให้ใช้

**Plausibility check สำหรับ consensus EBIT margin:** provider บางรายเติมค่า EBIT/EBITDA ปีอนาคตด้วยสูตรคงที่ (percentage ของ revenue) แทนการพยากรณ์รายปีจริง แม้ revenue consensus จะแปรผันตามปีจริง ให้ปฏิเสธ margin consensus (แต่ยังใช้ revenue consensus สำหรับ growth ต่อ) เมื่อ margin ของทุกปี consensus เกือบเท่ากันทุกปี (spread < 0.5 percentage point) **และ** ต่างจาก current sourced operating margin เกิน 20% โดยสัมพัทธ์

$$smoothstep(x)=3x^2-2x^3,\quad 0\le x\le1$$

$$Revenue_t=Revenue_{t-1}(1+g_t)$$

$$EBIT_t=Revenue_t\times Margin_t$$

$$NOPAT_t=EBIT_t(1-T)$$

### 4.2 Reinvestment

ใช้ level invested capital จาก filing แทนการหารด้วย revenue delta ปีเดียว:

$$Invested\ Capital=Book\ Equity+Debt-Cash$$

$$Sales/Capital=Revenue/Invested\ Capital$$

ถ้า operating-capital proxy ใช้ไม่ได้ อนุญาต fallback `Revenue / Total Assets` พร้อมระบุ basis; ถ้าทั้งคู่ไม่มีให้คืน missing input

$$Reinvestment_t=\frac{\max(Revenue_t-Revenue_{t-1},0)}{Sales/Capital}$$

$$FCFF_t=NOPAT_t-Reinvestment_t$$

ห้าม cap reinvestment เป็นสัดส่วนของ NOPAT เพราะจะทำให้ growth ดูเหมือนไม่ต้องใช้เงินทุน

### 4.3 Capitalized R&D

R&D ต้องเป็น annual consecutive USD observations อย่างน้อย 3 ปี อายุ research asset ปกติ 5 ปี และ 3 ปีสำหรับ software classification; หากประวัติสั้นกว่าอายุที่กำหนดให้ใช้ effective life ที่มีจริงและเปิดเผยว่า shortened

$$Amortization_t=\frac{\sum_{i=1}^{L}R\&D_{t-i}}{L}$$

$$Research\ Asset_t=R\&D_t+\sum_{i=1}^{L}R\&D_{t-i}\frac{L-i}{L}$$

$$Adjusted\ EBIT=Reported\ EBIT+R\&D_t-Amortization_t$$

$$Adjusted\ AfterTax\ Operating\ Income=Adjusted\ EBIT(1-T)+(R\&D_t-Amortization_t)T$$

เมื่อใช้ consensus EBIT ซึ่งเป็น reported/GAAP estimate ให้บวก `R&D EBIT adjustment / base revenue` เข้ากับ consensus EBIT margin และ mature margin ตลอดช่วงที่ใช้ Capitalized R&D พร้อมเปิดเผย reported consensus EBIT แยกจาก adjusted EBIT; adjustment ห้ามเป็น telemetry-only

`(R&D_t-Amortization_t)T` ต้องรวมอยู่ใน NOPAT ของทุก forecast year และ terminal year ที่ใช้ Capitalized R&D ไม่ใช่คำนวณเฉพาะ base-year telemetry เท่านั้น

เมื่อใช้ consensus อย่างน้อย 3 ปี ให้คำนวณ diagnostic ซ้ำโดยตัด consensus ปีสุดท้ายออกและคงสมมติฐานอื่นทั้งหมดไว้เหมือนเดิม หาก fair value เปลี่ยนตั้งแต่ 20% ของ full-consensus fair value ให้เปิดเผย warning code `LAST_CONSENSUS_YEAR_MATERIAL_DEPENDENCY`, ปีที่ตัด, fair value ทั้งสองค่า และ percentage delta การทดสอบนี้เป็น telemetry เท่านั้น ห้ามแทนที่หรือ cap fair value หลักที่ใช้ consensus ครบชุด

ถ้าประวัติ R&D ไม่ valid ให้ downgrade methodology เป็น Standard Driver-Based DCF พร้อม fallback reason; ห้ามสร้าง R&D schedule

### 4.4 Discounting and terminal value

$$DiscountFactor_t=\prod_{i=1}^{t}(1+WACC_i)^{-1}$$

$$PV(FCFF)=\sum_{t=1}^{n}FCFF_t\times DiscountFactor_t$$

Terminal economics ต้องเชื่อม growth กับ reinvestment:

$$Terminal\ ROIC=Terminal\ WACC$$

$$Terminal\ Reinvestment\ Rate=g/Terminal\ ROIC$$

$$Terminal\ FCFF=Terminal\ NOPAT(1-g/Terminal\ ROIC)$$

$$TV_n=\frac{Terminal\ FCFF}{Terminal\ WACC-g}$$

$$EV=PV(FCFF)+TV_n\times DiscountFactor_n$$

$$Equity\ Value=EV-Debt+Cash$$

$$Fair\ Value/Share=Equity\ Value/Current\ Shares\ Outstanding$$

## 5. Monte Carlo layer

- รัน 10,000 iterations เท่านั้น
- perturb stage-1 revenue growth และ operating/EBIT margin ด้วย historical volatility บน engine เดียวกับ deterministic result
- คืน `bear_p10`, `base_p50`, `bull_p90`, seed, valid sample count และ histogram telemetry
- ห้ามแทนค่าที่ invalid ด้วยราคาเดิม

## 6. Reverse DCF layer

Reverse DCF goal-seek stage-1 revenue growth และ target EBIT margin ให้ model fair value เข้าใกล้ live/target price ภายใน feasible bracket

- `implied_stage_1_revenue_cagr` และ `implied_target_ebit_margin` คือ solved drivers
- `implied_terminal_revenue_growth` และ `implied_terminal_ebit_margin` ต้องมาจากปลาย trajectory จริง ห้ามนำ stage-1 values ไปติดป้ายว่า terminal
- ต้องคืน year-N revenue, EBIT margin, FCFF และ horizon เพื่อให้ผู้ใช้เห็นขนาดธุรกิจที่ราคานั้นกำลังสมมติ
- ถ้า target อยู่นอก bracket ให้คืน empty `implied_expectations` และ machine-readable warning
- Reverse DCF เป็นคำอธิบายความคาดหวังของราคา ไม่ใช่หลักฐานว่า intrinsic value ถูกหรือผิด

## 7. Segment/SOTP evidence rule

แสดง segment ได้เมื่อเป็น filing-backed reported revenue mix พร้อม source/evidence เท่านั้น Revenue เพียงอย่างเดียวยังไม่พอสำหรับ segment valuation; หากไม่มี segment margin, reinvestment และ discount-rate inputs ให้สถานะ `EVIDENCE_ONLY` หรือ `UNAVAILABLE` และห้ามสร้าง “Core Business = 100% EV” เป็น segment valuation
