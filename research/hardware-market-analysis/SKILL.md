---
name: hardware-market-analysis
description: Compare hardware products for specific use cases with supply chain risk assessment, pricing predictions, and buy-now vs wait recommendations.
---

# Hardware Market Analysis — Buying Decisions with Supply Chain Risk

Use this skill when the user wants to compare hardware products for a specific use case (LLM inference, gaming, video editing, etc.) and needs pricing predictions, release date forecasts, and buy-now vs wait recommendations.

## When to use
- User asks to compare 3+ hardware options (GPUs, laptops, desktops, AI accelerators)
- User asks about price predictions, release dates, or "should I wait?"
- User mentions supply chain concerns, shortages, or component availability

## Step 1 — Product Research

Search for current specs, pricing, and release dates for all products. Use multiple queries:

```bash
web_search "<product_name> specs price 2025"
web_search "<product_name> specifications RAM GPU storage"
web_search "<product_name> vs <competitor> comparison"
```

Extract specs from official sources and detailed review sites. Focus on:
- Chip/processor details (cores, architecture, clock speeds)
- Memory (capacity, type, bandwidth) — **critical for AI workloads**
- Storage options and expandability
- Connectivity (ports, networking)
- Physical specs (dimensions, weight, power draw)
- OS compatibility

## Step 2 — Supply Chain & Market Analysis

**Always check for DRAM/memory shortages and component availability.** This is the #1 factor affecting pricing and release dates.

```bash
web_search "DRAM memory chip shortage 2025 2026 price forecast"
web_search "component shortage impact on <product_category>"
```

Key indicators to look for:
- DRAM price trends (DDR5, HBM)
- HBM production allocation (AI data centers vs consumer)
- Fab construction timelines (3-4 year cycle)
- OEM price increase warnings
- Delivery/lead time information

**Critical DRAM shortage context (as of 2026):**
- DRAM prices surged 70% in Q1 2026 after 50% increase in 2025
- AI data centers consume 70% of all memory chip production
- HBM production uses 3-4x cleanroom capacity per GB vs commodity DRAM
- Manufacturers prioritizing high-margin HBM over consumer DDR
- Meaningful supply relief not expected until 2027-2028
- Micron CEO quote: "customer-qualified bit output will land closer to 2028"

## Step 3 — New Product Leak & Release Date Research

Search for leaks, rumors, and official announcements about upcoming products:

```bash
web_search "<product> <next_generation> release date rumor leak"
web_search "<product> delay supply chain"
web_search "<chip_vendor> roadmap 2026 2027"
```

Key sources:
- Tech journalists (Gurman for Apple, Engadget, Tom's Hardware)
- Reddit communities (r/MacStudio, r/Amd, r/LocalLLaMA)
- Developer forums (NVIDIA forums, AMD forums)
- Manufacturer press releases and blog posts
- Supply chain analysts (IDC, TechInsights)

Track:
- Expected release windows
- Delay reasons (supply chain, technical, strategic)
- Delay probability assessment
- Configuration changes (memory options removed, specs adjusted)

## Step 4 — Price Prediction

Combine current pricing with supply chain data:

**DRAM shortage price impacts:**
- DDR5 32GB kits: $120 → $180 → $250-280 (Q3 2026)
- DDR5 128GB server: $800 → ~$1,360
- Workstation upgrade (32GB→64GB): +$200-300 vs 2025 pricing
- PC average selling prices: +4-8% (IDC), some vendors warn +15-20%

**Prediction formula:**
- Base price increase = current MSRP × (1 + DRAM inflation factor)
- Memory config penalty: +$200-300 per memory tier jump
- Supply delay premium: +$100-200 if product is delayed (reduced competition)
- New generation premium: +$200-400 for feature upgrades

## Step 5 — Decision Framework

Present results in these sections:

### A. Specifications Comparison Table
Compare all products side-by-side on key metrics relevant to the use case.

### B. Inference/Performance Comparison
Where available, include real benchmark data (not just theoretical specs).
- For AI: include tokens/sec for specific models
- For creative work: include specific software benchmarks
- Note the bottleneck factor (memory bandwidth vs compute)

### C. Price Predictions with Confidence Levels
- Product name: predicted price range (+/- $X) with reasoning
- Confidence level: high (official pricing available), medium (trend extrapolation), low (speculative)

### D. Release Timeline & Delay Risk
- Expected release window
- Delay probability: high/medium/low with reasoning
- If delayed, revised expected window

### E. Buy Now vs Wait Recommendation
Present a clear recommendation matrix:
| Your situation | Recommendation |
| Need it now | Buy X now |
| Can wait 1-3 months | Wait for Y |
| Can wait 3-6 months | Wait for Z |
| Budget constrained | Buy X (current gen) |

## Key Insights to Always Include

1. **Memory bandwidth is the #1 bottleneck for inference** — not compute. Unified memory architectures (Apple, AMD APU, NVIDIA Grace) often outperform discrete GPUs at same price for LLM inference.

2. **HBM vs DDR5 trade-off** — AI data center demand is structurally shifting DRAM supply. This is not a temporary disruption but a permanent reallocation.

3. **MoE models change the math** — Active parameters matter more than total parameters for decode speed. Frame recommendations around active parameter counts.

4. **Upgrade path matters** — Products with soldered memory (Apple, some APUs) lock you in at purchase. Products with upgradeable RAM (traditional PCs) offer future flexibility.

## Output Format
- Use markdown tables (not LaTeX)
- Include all search results as URLs
- Be specific with numbers (not "expensive" but "$2,000-$3,000")
- Give confidence levels for predictions
- Include "buy now" vs "wait" scenarios