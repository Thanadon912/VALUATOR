import numpy as np
from scipy.optimize import brentq
from dataclasses import dataclass
from typing import Optional

@dataclass
class Segment:
    base_revenue: float
    target_margin: float
    sales_to_capital: float
    growth_profile: np.ndarray
    wacc: float

def generate_s_curve(initial_growth: float, terminal_growth: float, periods: int = 15, decay_rate: float = 0.3) -> np.ndarray:
    """
    Generate an S-curve for growth rates over time.
    growth_t = terminal_growth + (initial_growth - terminal_growth) * exp(-decay_rate * t)
    """
    t = np.arange(0, periods)
    return terminal_growth + (initial_growth - terminal_growth) * np.exp(-decay_rate * t)

def calculate_segment_ev(segment: Segment, tax_rate: float, terminal_growth: float) -> float:
    """
    Calculate the Enterprise Value of a single segment.
    """
    periods = len(segment.growth_profile)
    
    # 1. Revenue
    # Cumulative product of (1 + growth_rate)
    growth_multipliers = 1 + segment.growth_profile
    cumulative_growth = np.cumprod(growth_multipliers)
    revenues = segment.base_revenue * cumulative_growth
    
    # Prepend base revenue for reinvestment calculation
    revenues_with_base = np.insert(revenues, 0, segment.base_revenue)
    revenue_changes = np.diff(revenues_with_base)
    
    # 2. NOPAT
    nopats = revenues * segment.target_margin * (1 - tax_rate)
    
    # 3. Reinvestment
    # Floor at 0 if revenue drops
    reinvestments = np.maximum(revenue_changes, 0) / segment.sales_to_capital
    
    # 4. FCF
    fcfs = nopats - reinvestments
    
    # 5. Terminal Value
    terminal_fcf = fcfs[-1]
    
    # Validate denominator for TV
    if segment.wacc <= terminal_growth:
        raise ValueError(f"WACC ({segment.wacc}) must be greater than terminal growth ({terminal_growth})")
        
    tv = (terminal_fcf * (1 + terminal_growth)) / (segment.wacc - terminal_growth)
    
    # 6. Discounting
    t = np.arange(1, periods + 1)
    discount_factors = (1 + segment.wacc) ** t
    
    pv_fcfs = np.sum(fcfs / discount_factors)
    pv_tv = tv / ((1 + segment.wacc) ** periods)
    
    return float(pv_fcfs + pv_tv)

def solve_implied_ai_growth(
    target_stock_price: float,
    hw_base_revenue: float,
    hw_margin: float,
    hw_sales_to_capital: float,
    hw_growth_rate: float,
    hw_wacc: float,
    sw_base_revenue: float,
    sw_margin: float,
    sw_sales_to_capital: float,
    sw_wacc: float,
    tax_rate: float,
    terminal_growth: float,
    net_cash: float,
    total_debt: float,
    shares_outstanding: float,
    periods: int = 15,
    decay_rate: float = 0.3
) -> dict:
    
    # 1. Fix the Hardware Segment's growth
    # Flat growth array for hardware
    hw_growth_profile = np.full(periods, hw_growth_rate)
    hw_segment = Segment(
        base_revenue=hw_base_revenue,
        target_margin=hw_margin,
        sales_to_capital=hw_sales_to_capital,
        growth_profile=hw_growth_profile,
        wacc=hw_wacc
    )
    hw_ev = calculate_segment_ev(hw_segment, tax_rate, terminal_growth)
    
    def objective_function(implied_ai_growth: float) -> float:
        sw_growth_profile = generate_s_curve(implied_ai_growth, terminal_growth, periods, decay_rate)
        sw_segment = Segment(
            base_revenue=sw_base_revenue,
            target_margin=sw_margin,
            sales_to_capital=sw_sales_to_capital,
            growth_profile=sw_growth_profile,
            wacc=sw_wacc
        )
        sw_ev = calculate_segment_ev(sw_segment, tax_rate, terminal_growth)
        total_ev = hw_ev + sw_ev
        calculated_price = (total_ev + net_cash - total_debt) / shares_outstanding
        return calculated_price - target_stock_price
        
    try:
        implied_growth = brentq(objective_function, 0.0, 1.5)
        
        # Calculate final values for the report
        final_sw_growth_profile = generate_s_curve(implied_growth, terminal_growth, periods, decay_rate)
        final_sw_segment = Segment(
            base_revenue=sw_base_revenue,
            target_margin=sw_margin,
            sales_to_capital=sw_sales_to_capital,
            growth_profile=final_sw_growth_profile,
            wacc=sw_wacc
        )
        final_sw_ev = calculate_segment_ev(final_sw_segment, tax_rate, terminal_growth)
        
        return {
            "status": "success",
            "implied_ai_growth": implied_growth,
            "hw_ev": hw_ev,
            "sw_ev": final_sw_ev,
            "total_ev": hw_ev + final_sw_ev,
            "target_price": target_stock_price,
            "calculated_price": (hw_ev + final_sw_ev + net_cash - total_debt) / shares_outstanding
        }
    except ValueError as e:
        return {
            "status": "failed",
            "reason": str(e)
        }
