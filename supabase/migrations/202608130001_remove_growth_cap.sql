alter table public.valuation_assumptions drop constraint valuation_assumptions_growth_range;
alter table public.valuation_assumptions add constraint valuation_assumptions_growth_range check (stage_1_growth_rate >= 0.0);
