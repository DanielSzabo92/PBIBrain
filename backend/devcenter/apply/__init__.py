"""Local apply of a Change Plan (technical design sections 13 and 16 S9).

The modules: ``steps`` (step IDs and guard checks), ``desktop`` (Desktop-open
check), ``pipeline`` (write, guard, and promotion through ``change_guard``),
``rescan`` (compare of the target with the plan), ``report`` (Markdown change
report), and ``service`` (the apply sequence, its progress, and undo).
"""
