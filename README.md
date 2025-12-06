<!-- =========================================================
     Financial Major Risk Task Force – CODEx
     Black & Red Intelligence Design · Ready to Copy/Paste
     ========================================================= -->

<div align="center">

  <!-- Animated Title -->
  <img 
    src="https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=700&size=28&pause=1000&color=FF0033&center=true&vCenter=true&width=750&lines=Financial+Major+Risk+Task+Force;Offline+AML+%2F+Fraud+Intelligence+Environment;FMRTF" 
    alt="FMRTF Title Animation"
/>

<br/><br/>

  <!-- Badges -->
  <img src="https://img.shields.io/badge/Project-FMRTF-000000?style=for-the-badge&labelColor=000000&color=FF0033" />
  <img src="https://img.shields.io/badge/Domain-AML%20%7C%20Fraud%20%7C%20KYC-000000?style=for-the-badge&labelColor=000000&color=8B0000" />
  <img src="https://img.shields.io/badge/Mode-OFFLINE-000000?style=for-the-badge&labelColor=000000&color=FF0033" />
  <img src="https://img.shields.io/badge/Stack-Python%20%7C%20SQLite%20%7C%20PySide6-000000?style=for-the-badge&labelColor=000000&color=8B0000" />

</div>

---

## 🧩 Overview

**Financial Major Risk Task Force** is an **offline intelligence environment** for  
**Anti-Money Laundering (AML), Fraud, KYC and CFT analysis**.

The system is designed to:

- simulate **realistic financial crime scenarios**,  
- support **analysts under real pressure**, and  
- keep all data **local, traceable and auditable** – no cloud, no external calls.

---

## 🎯 Mission

> Build a compact, high-integrity investigation suite that treats financial crime  
> the way task forces do: structured, documented, and technically precise.

**Core goals:**

- 🛡️ **Offline & self-contained** – no external dependencies  
- 🔎 **Pattern-focused** – typologies, structuring, layering, anomalies  
- 🧠 **Analyst-first** – workflows built for investigations, not just dashboards  
- 📚 **Auditproof** – every action leaves a verifiable trace  

---

## 🛠 Feature Set

### 1️⃣ Case & Alert Engine
- Central alert inbox (severity, typology, source)
- Full case lifecycle: **Open → Investigate → Escalate → Close**
- Analyst notes, evidence fields, decision logs
- Automatic **audit trail** for every state change

### 2️⃣ Customer Intelligence
- Customer profiles with KYC / CDD attributes
- Risk flags: PEP, high-risk country, product risk, channel risk
- Relationship mapping (UBOs, links, shared attributes)
- Behavioral indicators based on transaction history

### 3️⃣ Transaction Analysis
- Local transaction storage (SQLite)
- Scenario-based risk patterns, e.g.:
  - structuring / smurfing
  - round-tripping
  - fast in/fast out movement
- Counterparty and flow overviews

### 4️⃣ Security & Access
- 🔐 bcrypt-based user authentication
- Role model (Analyst / Senior / Admin)
- Optional inactivity lock for analyst desks
- Full local data control – **no external API calls**

### 5️⃣ Data Layer
- Lightweight, file-based **SQLite** datastore
- Explicit schemas for:
  - customers
  - transactions
  - alerts
  - cases
  - audit logs
- Designed for reproducibility and forensic review

---

## 🧱 Architecture Snapshot

```text
[ Analyst UI (PySide6) ]
        │
        ▼
[ Application Core (Python) ]
        │
        ├── Case & Alert Engine
        ├── Customer Intelligence Layer
        ├── Transaction Analysis Module
        └── Security / Auth (bcrypt, roles)
        │
        ▼
[ SQLite Data Store (fully offline) ]
