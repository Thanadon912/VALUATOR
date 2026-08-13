from typing import List
from pydantic import BaseModel
import numpy as np
from scipy.optimize import brentq
from app.services.sotp_reverse_dcf import generate_s_curve, calculate_segment_ev, Segment

class SegmentConfig(BaseModel):
    name: str
    base_revenue: float
    target_margin: float
    sales_to_capital: float
    is_high_growth: bool

class CompanyConfig(BaseModel):
    ticker: str
    sector: str
    current_price: float
    shares_outstanding: float
    net_cash: float
    wacc: float
    segments: List[SegmentConfig]

class DynamicSOTPReverseDCFEngine:
    def __init__(self, periods: int = 15, decay_rate: float = 0.3, tax_rate: float = 0.15, terminal_growth: float = 0.02):
        self.periods = periods
        self.decay_rate = decay_rate
        self.tax_rate = tax_rate
        self.terminal_growth = terminal_growth
        
    def solve(self, config: CompanyConfig) -> dict:
        high_growth_segments = [s for s in config.segments if s.is_high_growth]
        if len(high_growth_segments) != 1:
            raise ValueError(f"Exactly ONE segment must have is_high_growth=True, found {len(high_growth_segments)}")
            
        hg_config = high_growth_segments[0]
        standard_configs = [s for s in config.segments if not s.is_high_growth]
        
        # 1. Calculate EV for all standard segments (assume 5% flat growth for standard segments)
        standard_evs = []
        standard_details = {}
        hw_growth_profile = np.full(self.periods, 0.05)
        for sc in standard_configs:
            seg = Segment(
                base_revenue=sc.base_revenue,
                target_margin=sc.target_margin,
                sales_to_capital=sc.sales_to_capital,
                growth_profile=hw_growth_profile,
                wacc=config.wacc
            )
            ev = calculate_segment_ev(seg, self.tax_rate, self.terminal_growth)
            standard_evs.append(ev)
            standard_details[sc.name] = ev
            
        total_standard_ev = sum(standard_evs)
        
        # 2. Objective function for Brentq
        def objective_function(implied_growth: float) -> float:
            sw_growth_profile = generate_s_curve(implied_growth, self.terminal_growth, self.periods, self.decay_rate)
            sw_seg = Segment(
                base_revenue=hg_config.base_revenue,
                target_margin=hg_config.target_margin,
                sales_to_capital=hg_config.sales_to_capital,
                growth_profile=sw_growth_profile,
                wacc=config.wacc
            )
            sw_ev = calculate_segment_ev(sw_seg, self.tax_rate, self.terminal_growth)
            total_ev = total_standard_ev + sw_ev
            
            # total_ev + net_cash (cash - debt) = equity_value
            calculated_price = (total_ev + config.net_cash) / config.shares_outstanding
            return calculated_price - config.current_price
            
        try:
            # We widen bounds to 10.0 to safely capture massive expectations
            implied_growth = brentq(objective_function, -0.5, 10.0)
            
            # Re-run with final implied growth
            final_sw_growth_profile = generate_s_curve(implied_growth, self.terminal_growth, self.periods, self.decay_rate)
            final_sw_seg = Segment(
                base_revenue=hg_config.base_revenue,
                target_margin=hg_config.target_margin,
                sales_to_capital=hg_config.sales_to_capital,
                growth_profile=final_sw_growth_profile,
                wacc=config.wacc
            )
            final_hg_ev = calculate_segment_ev(final_sw_seg, self.tax_rate, self.terminal_growth)
            
            return {
                "status": "success",
                "ticker": config.ticker,
                "target_price": config.current_price,
                "implied_high_growth_rate": implied_growth,
                "high_growth_segment_name": hg_config.name,
                "high_growth_ev": final_hg_ev,
                "standard_evs": standard_details,
                "total_ev": total_standard_ev + final_hg_ev,
                "calculated_price": (total_standard_ev + final_hg_ev + config.net_cash) / config.shares_outstanding
            }
        except ValueError as e:
            return {
                "status": "failed",
                "ticker": config.ticker,
                "reason": str(e)
            }

class ValuationRouter:
    def __init__(self):
        self.sotp_engine = DynamicSOTPReverseDCFEngine()
        
    def route_and_evaluate(self, config: CompanyConfig) -> dict:
        normalized_sector = config.sector.lower()
        if "financial" in normalized_sector or "bank" in normalized_sector:
            raise NotImplementedError("Financial sector requires a DDM/FCFE engine, which is not yet implemented.")
        elif any(term in normalized_sector for term in ("technology", "software", "auto", "semiconductor")):
            return self.sotp_engine.solve(config)
        else:
            raise ValueError(f"Unknown sector: {config.sector}")
