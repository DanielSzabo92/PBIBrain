# Power BI Brain

Canonical language for Power BI project ingestion and the semantic graph it produces.

## Language

**PBIP Project**:
A source-controlled Power BI project containing report and semantic model artifacts.
_Avoid_: PBIX project

**Semantic Model Artifact**:
A Power BI model definition stored as TMDL or TMSL.
_Avoid_: Dataset, model folder

**Report Artifact**:
A Power BI report definition stored as PBIR or PBIR-Legacy.
_Avoid_: Report file

**TMDL**:
The folder-based, text form of a semantic model definition.
_Avoid_: TMSL

**TMSL**:
The JSON form of a semantic model definition.
_Avoid_: TMDL

**PBIR**:
The folder-based, public-schema form of a report definition.
_Avoid_: PBIR-Legacy

**PBIR-Legacy**:
The single-document legacy form of a report definition.
_Avoid_: PBIR

**Local Model Reference**:
A report binding to a semantic model artifact in the same project.
_Avoid_: Remote connection

**Remote Model Reference**:
A report binding to a semantic model outside the project.
_Avoid_: Local model link
