from dataclasses import dataclass


@dataclass(frozen=True)
class CustomerMixIndustryCase:
    sector: str
    industry: str
    ticker: str
    filing_text: str
    customer_labels: tuple[str, ...]
    end_markets: tuple[str, ...] = ()


CUSTOMER_MIX_INDUSTRY_CASES = (
    CustomerMixIndustryCase(
        sector="Information Technology",
        industry="Semiconductors",
        ticker="TSM",
        filing_text=(
            "Our customers include fabless semiconductor companies, system "
            "companies, and integrated device manufacturers. Our end markets "
            "include high performance computing and smartphones."
        ),
        customer_labels=(
            "fabless semiconductor companies",
            "system companies",
            "integrated device manufacturers",
        ),
        end_markets=("high performance computing", "smartphones"),
    ),
    CustomerMixIndustryCase(
        sector="Financials",
        industry="Diversified Banks",
        ticker="JPM",
        filing_text=(
            "Our customers include consumers, small businesses, corporations, "
            "financial institutions, and government entities. The customer "
            "base spans consumer banking and commercial banking markets."
        ),
        customer_labels=(
            "consumers",
            "small businesses",
            "corporations",
            "financial institutions",
            "government entities",
        ),
        end_markets=("consumer banking", "commercial banking"),
    ),
    CustomerMixIndustryCase(
        sector="Health Care",
        industry="Managed Health Care",
        ticker="UNH",
        filing_text=(
            "Our customers include employers, government entities, health "
            "plans, care providers, and individual consumers. We serve the "
            "commercial insurance and public health program markets."
        ),
        customer_labels=(
            "employers",
            "government entities",
            "health plans",
            "care providers",
            "individual consumers",
        ),
        end_markets=(
            "commercial insurance",
            "public health program",
        ),
    ),
    CustomerMixIndustryCase(
        sector="Industrials",
        industry="Construction Machinery",
        ticker="CAT",
        filing_text=(
            "Our customers include construction contractors, mining "
            "companies, energy producers, and transportation operators. "
            "Our end markets include construction, mining, energy, and rail."
        ),
        customer_labels=(
            "construction contractors",
            "mining companies",
            "energy producers",
            "transportation operators",
        ),
        end_markets=("construction", "mining", "energy", "rail"),
    ),
    CustomerMixIndustryCase(
        sector="Consumer Discretionary",
        industry="Broadline Retail",
        ticker="AMZN",
        filing_text=(
            "Our customers include consumers, sellers, developers, "
            "enterprises, and content creators. Our end markets include "
            "online retail, cloud computing, advertising, and entertainment."
        ),
        customer_labels=(
            "consumers",
            "sellers",
            "developers",
            "enterprises",
            "content creators",
        ),
        end_markets=(
            "online retail",
            "cloud computing",
            "advertising",
            "entertainment",
        ),
    ),
    CustomerMixIndustryCase(
        sector="Consumer Staples",
        industry="Household Products",
        ticker="PG",
        filing_text=(
            "Our customers include mass merchandisers, grocery stores, "
            "pharmacies, distributors, and consumers. Our end markets include "
            "beauty, grooming, health care, fabric care, and family care."
        ),
        customer_labels=(
            "mass merchandisers",
            "grocery stores",
            "pharmacies",
            "distributors",
            "consumers",
        ),
        end_markets=(
            "beauty",
            "grooming",
            "health care",
            "fabric care",
            "family care",
        ),
    ),
    CustomerMixIndustryCase(
        sector="Energy",
        industry="Integrated Oil and Gas",
        ticker="XOM",
        filing_text=(
            "Our customers include refiners, chemical manufacturers, "
            "industrial users, wholesalers, and government entities. Our end "
            "markets include transportation fuels, lubricants, chemicals, "
            "and power generation."
        ),
        customer_labels=(
            "refiners",
            "chemical manufacturers",
            "industrial users",
            "wholesalers",
            "government entities",
        ),
        end_markets=(
            "transportation fuels",
            "lubricants",
            "chemicals",
            "power generation",
        ),
    ),
    CustomerMixIndustryCase(
        sector="Utilities",
        industry="Electric Utilities",
        ticker="NEE",
        filing_text=(
            "Our customers include residential customers, commercial "
            "customers, industrial customers, municipalities, and wholesale "
            "power purchasers. Our end markets include regulated electricity "
            "and renewable power generation."
        ),
        customer_labels=(
            "residential customers",
            "commercial customers",
            "industrial customers",
            "municipalities",
            "wholesale power purchasers",
        ),
        end_markets=(
            "regulated electricity",
            "renewable power generation",
        ),
    ),
    CustomerMixIndustryCase(
        sector="Real Estate",
        industry="Industrial REITs",
        ticker="PLD",
        filing_text=(
            "Our customers include retailers, manufacturers, logistics "
            "providers, transportation companies, and e-commerce companies. "
            "Our end markets include distribution, fulfillment, and logistics."
        ),
        customer_labels=(
            "retailers",
            "manufacturers",
            "logistics providers",
            "transportation companies",
            "e-commerce companies",
        ),
        end_markets=("distribution", "fulfillment", "logistics"),
    ),
    CustomerMixIndustryCase(
        sector="Communication Services",
        industry="Integrated Telecommunication Services",
        ticker="VZ",
        filing_text=(
            "Our customers include consumers, small businesses, enterprises, "
            "public sector entities, and wholesale carriers. Our end markets "
            "include wireless communications, broadband, and enterprise "
            "network services."
        ),
        customer_labels=(
            "consumers",
            "small businesses",
            "enterprises",
            "public sector entities",
            "wholesale carriers",
        ),
        end_markets=(
            "wireless communications",
            "broadband",
            "enterprise network services",
        ),
    ),
    CustomerMixIndustryCase(
        sector="Materials",
        industry="Industrial Gases",
        ticker="LIN",
        filing_text=(
            "Our customers include hospitals, chemical manufacturers, metal "
            "producers, food processors, and electronics manufacturers. Our "
            "end markets include health care, chemicals, metals, food and "
            "beverage, and electronics."
        ),
        customer_labels=(
            "hospitals",
            "chemical manufacturers",
            "metal producers",
            "food processors",
            "electronics manufacturers",
        ),
        end_markets=(
            "health care",
            "chemicals",
            "metals",
            "food and beverage",
            "electronics",
        ),
    ),
)
