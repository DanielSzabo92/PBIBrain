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

**Merge Session**:
One saved unit of work that brings objects from many sources into one target model and one target report.
_Avoid_: Merge project, workspace

**Target**:
The semantic model or report that receives the changes in a merge session. It can be an existing source, a new empty item, or a copy of a source.
_Avoid_: Master, baseline

**Donor**:
A source in a merge session that is not the target. A donor is never changed.
_Avoid_: Source model, origin

**Alignment**:
The link between objects in different sources that are "the same object", also when their names are different.
_Avoid_: Mapping, match

**Change Plan**:
The ordered list of operations that the merge session will do to the target, with the prerequisites included.
_Avoid_: Script, deployment

**Breaks**:
The objects that stop to work or change their result because of a change.
_Avoid_: Downstream impact

**Needs**:
The objects that the target must have before an added object can work.
_Avoid_: Upstream impact, dependencies

**Merge Choice**:
The choice for one aligned row in a merge session: keep the target, take from a donor, take some parts, add with a new name, remove, or skip.
_Avoid_: Decision (that word means review decisions)

**Alignment Key**:
The value that tells that two objects in different sources are the same object. The lineageTag is the first alignment key. Objects with no lineageTag use other keys, for example the two columns of a relationship.
_Avoid_: Match key, ID

**Strict Compare**:
The compare mode that compares the exact text and the annotations. The default compare ignores formatting differences that do not change the model.
_Avoid_: Exact mode, raw diff

**Plan Step**:
One item of the Change Plan that comes from one Merge Choice or one prerequisite. The app counts plan steps in the plan summary.
_Avoid_: Operation, task

**Operation**:
One atomic change to the target that a plan step compiles to, for example one expression rewrite or one field rebind.
_Avoid_: Step, action

**Removal Policy**:
The rule that tells what happens to the dependents of a removed object: Block, Cascade, or Repoint. The user sets it for each removed object.
_Avoid_: Delete mode
