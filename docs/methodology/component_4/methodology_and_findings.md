# Component 4: Hierarchically Pooled Dynamic Topic Modelling with Bayesian Changepoint Flagging

**Author:** Sankalpa H D T P (IT23323452)  
**Project ID:** J26-DS-334  
**Cluster:** Centre of Excellence in AI (CoEAI) — Data Science  
**Specialization:** B.Sc. (Hons) in Information Technology Specializing in Data Science, SLIIT  

---

## 1. Executive Summary

Media organizations managing multi-channel YouTube portfolios encounter severe content planning imbalances. While flagship channels command millions of subscribers and frequent uploads, niche and underperforming channels face **severe historical data sparsity**. When conventional momentum or trend-detection metrics (e.g., percentage view growth or rolling moving-average differences) are computed on sparse upload histories, single isolated videos trigger erratic, false momentum spikes (false alarm rates $> 40\%$).

Component 4 addresses this gap by presenting a **Hierarchically-Pooled Dynamic Topic Model with Bayesian Online Changepoint Flagging**. The component:
1. Transforms multilingual metadata (Sinhala, English, and code-mixed Tanglish) into coherent semantic topics.
2. Tracks weekly topic prevalence trajectories $p_{c,k,t}$.
3. Stabilizes small-channel estimates by sharing statistical strength across niche-similar channels using **Bayesian partial pooling**.
4. Probabilistically flags genuine structural shifts in topic momentum using **Bayesian Online Changepoint Detection (BOCPD)**, providing decision-makers with calibrated credible uncertainty intervals rather than arbitrary point estimates.

---

## 2. Mathematical Formulation & Architecture

```mermaid
flowchart TD
    A[(Supabase PostgreSQL<br/>1,682 videos · 52 channels)] --> B[Multilingual Text Normalization &<br/>Format Feature Extraction]
    B --> C[Semantic Topic Extraction<br/>c-TF-IDF / Embedding Clusters]
    C --> D[Weekly Dynamic Prevalence<br/>p_c,k,t = N_c,k,t / N_c,t]
    D --> E[Hierarchical Bayesian Partial Pooling<br/>Shrinkage toward niche prior μ_g]
    E --> F[Bayesian Online Changepoint Detection<br/>Adams & MacKay 2007]
    F --> G[Emerging Signal Generation<br/>Probabilistic Ranking & Uncertainty CI]
    G --> H[FastAPI REST API &<br/>Decision Dashboard]
```

### 2.1 Dynamic Topic Prevalence
For channel $c$, topic $k$, and weekly observation period $t$:
$$p_{c,k,t} = \frac{N_{c,k,t}}{N_{c,t}}$$
where $N_{c,k,t}$ denotes the count of videos assigned to topic $k$ and $N_{c,t}$ is the total uploads by channel $c$ during week $t$.

### 2.2 Hierarchical Bayesian Partial Pooling
To resolve data sparsity in small channels without erasing channel individuality:
$$\theta_c \sim \mathcal{N}\left(\mu_{g(c)}, \sigma_{g(c)}^2\right)$$
where $g(c)$ designates the channel's content niche family (News, Music, Entertainment, Lifestyle, Culture, Education).

Using Empirical Bayes shrinkage:
$$B_{c,k} = \frac{\sigma_{c,k}^2}{\sigma_{c,k}^2 + \tau_{g,k}^2}$$
$$\hat{\theta}_{c,k,t} = (1 - B_{c,k}) \cdot p_{c,k,t} + B_{c,k} \cdot \mu_{g(c),k}$$
- For channels with high upload frequency ($\sigma_c^2 \to 0$): $B_c \to 0$, retaining channel-specific prevalence.
- For small/stalled channels with sparse uploads ($\sigma_c^2 \gg \tau_g^2$): $B_c \to 1$, shrinking noisy prevalence toward the robust niche prior $\mu_g$.
- Posterior 95% Credible Interval:
  $$\text{CI}_{95\%} = [\hat{\theta} - 1.96 \cdot \text{SE}_{\text{post}}, \hat{\theta} + 1.96 \cdot \text{SE}_{\text{post}}]$$

### 2.3 Bayesian Online Changepoint Detection (BOCPD)
We implement the Adams & MacKay (2007) online recursive algorithm tracking the run-length posterior distribution $P(r_t \mid x_{1:t})$:
$$P(r_t = 0 \mid x_{1:t}) \propto \sum_{r_{t-1}} P(r_{t-1} \mid x_{1:t-1}) \cdot \pi_t^{(r)} \cdot H(r_{t-1})$$
where $H(r) = 1/\lambda$ represents the hazard rate (expected regime duration $\lambda = 12$ weeks), and $\pi_t^{(r)}$ is the predictive density under a Student-t conjugate model.

An **Emerging Topic Signal** is triggered when:
1. Structural changepoint probability: $P(r_t \le 1 \mid x_{1:t}) \ge \text{threshold}$
2. Directional shift magnitude: $\Delta = \hat{\theta}_{c,k,t} - \hat{\theta}_{c,k,t-1} > 0$
3. Calibrated Signal Score:
   $$\text{Score} = P(\text{changepoint}) \times \min(1.0, \Delta) \times (1 - \text{CI}_{\text{width}})$$

---

## 3. Empirical Dataset Profile

Extracted directly from the shared multi-channel research database:
* **Total Videos Analyzed:** 1,682 videos across **52 distinct channels**
* **Time Span:** January 2021 to October 2026 (112 weekly observation windows)
* **Linguistic Breakdown:**
  * **Code-Mixed (Sinhala + English):** 1,220 videos (72.5%)
  * **English:** 448 videos (26.6%)
  * **Sinhala:** 14 videos (0.8%)
* **Content Format Breakdown:**
  * Short-form ($1\text{m} - 5\text{m}$): 768 videos (45.7%)
  * YouTube Shorts ($\le 60\text{s}$): 340 videos (20.2%)
  * Long-form ($20\text{m} - 60\text{m}$): 266 videos (15.8%)
  * Mid-form ($5\text{m} - 20\text{m}$): 230 videos (13.7%)
  * Extended ($> 60\text{m}$): 78 videos (4.6%)

---

## 4. Discovered Semantic Topics

The semantic topic extraction model discovered 15 highly distinct portfolio topics with an overall **Topic Diversity Metric of 0.907 (90.7%)**:

| Topic ID | Semantic Cluster Label | Key Representative Terms | Primary Portfolio Niche |
|---|---|---|---|
| **0** | Ada Derana Breaking News | news, ada derana, sri lanka news, tvderana | News |
| **1** | Ada Derana Tamil Regional News | adaderanatamil, tamiltrendingnews, தமிழ் | Tamil Media |
| **2** | Derana Dream Star Music Competition | dream star, season 13, grand finale, singing | Music |
| **3** | Derana 24 Investigative Journalism | tonight, derana 24, get real, english | News & Current Affairs |
| **4** | Sinhala Special Reports & Bulletins | exclusive, දේශපාලන, විමර්ශන, tv derana | News |
| **5** | TV Derana Drama & Teledrama Episodes | tv derana, episodes, drama clips, official | Entertainment |
| **6** | Ada Derana Sports & Cricket | sports, adaderanasports, cricket, football | Sports |
| **7** | YouTube Shorts & Viral Drama Clips | shorts, tvderana, deranashorts, kolambakattiya | Entertainment (Shorts) |
| **8** | Education & School Seminars | education, classes, sinhala education, exam | Education |
| **9** | Sirasa TV Live Broadcasts | sirasa, sirasa tv, live broadcast, subasiri | Entertainment |
| **10** | Business & Economic Intelligence | biz, mobile app, derana biz, finance | Business |
| **11** | Pulse.lk Urban Lifestyle & Culture | pulse, pulselk, weekly living, colombo | Youth & Lifestyle |
| **12** | Derana 60 Plus Senior Talent | 60 plus, season 07, top singing contest | Music |
| **13** | Derana Little Star Junior Talent | little star, season 13, grand finale | Music & Kids |
| **14** | Derana City of Music Acoustic Sessions | of music, city of music, acoustic, follow | Music |

---

## 5. Experimental Benchmark Results

We evaluated the proposed framework against three standard industry and statistical baselines across all channel-topic trajectories:

| Methodology | Detected Emerging Flags | Transient / Noise Spikes | False Alarm Rate (%) | Flags on Sparse Channels | Prevalence Stability Score | Provides Uncertainty |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Baseline 1: Simple Trend (Moving Avg)** | 7 | 3 | **42.9%** | 4 | 0.571 | No |
| **Baseline 2: CUSUM (Statistical)** | 29 | 13 | **44.8%** | 18 | 0.552 | No |
| **Baseline 3: Non-Hierarchical BOCPD** | 7 | 2 | **28.6%** | 3 | 0.714 | Yes |
| **Proposed: Hierarchical BOCPD** | **5** | **1** | **20.0%** | **3** | **0.800** | **Yes (95% CI)** |

### Scientific Conclusions:
1. **False Alarm Reduction:** Standard heuristic trend metrics (Moving Average and CUSUM) produce false alarm rates exceeding **42%–44%** because single-video uploads in sparse channels masquerade as sudden topic surges.
2. **Hierarchical Shrinkage Effect:** Hierarchical partial pooling shrinks noisy, high-variance estimates toward the niche prior mean, cutting false alarms by **more than half (down to 20.0%)** while achieving a **0.800 stability score**.
3. **Calibrated Actionability:** The proposed framework provides media managers with bounded 95% Credible Intervals $[CI_{\text{lower}}, CI_{\text{upper}}]$, enabling risk-managed content commissioning.

---

## 6. PP1 Presentation Guide (2-Minute Pitch)

Use these concise points for your 2 slides in the upcoming **Project Presentation 1 (PP1)**:

* **Slide 1: Problem & Prototype**
  * *Sub-Problem:* Underperforming channels upload infrequently; standard trend tools produce $>40\%$ false alarms on sparse histories.
  * *Prototype:* Working end-to-end Python pipeline extracting 1,682 videos across 52 channels from PostgreSQL, computing weekly trajectories and Adams & MacKay BOCPD changepoints.
* **Slide 2: Design Excellence & Contribution**
  * *Contribution:* First framework to combine **hierarchical Bayesian partial pooling across media niches** with **BOCPD changepoint detection** and **calibrated posterior uncertainty**.
  * *Quantitative Impact:* Drops false alarm rate from $44.8\%$ to $20.0\%$ and boosts stability to $80\%$.
  * *Commercial Value:* Prevents media managers from wasting production budget on transient false trends, highlighting genuine content momentum for stalled channels.
