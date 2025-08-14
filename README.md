# Essay Writer

[![Open Essay Writer Notebook](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/rajsiddarth/agent-Essay-Writer/main?labpath=agent-%20Essay%20Writer.ipynb)


**Essay Writer** generates high-quality, research-informed essays through a structured workflow.  
It guides the user from topic planning to final revisions, integrating research queries and iterative critique handling.

---

## 📌 Overview

The system breaks down essay creation into distinct stages:
1. **Plan** – Create a high-level outline for the essay.
2. **Research Plan** – Formulate search queries to gather relevant information.
3. **Generate** – Write a 5-paragraph essay based on the plan and research.
4. **Reflect** – Review and improve based on critique.
5. **Research Critique** – Refine content using additional research if necessary.

---

## 🛠 Workflow

```mermaid
flowchart TD
    A[Plan] --> B[Research Plan]
    B --> C[Generate]
    C -->|Continue| D[Reflect]
    D --> E[Research Critique]
    E --> C
