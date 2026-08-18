"""Three adapters, one shape.

Competitor posts, tweets and RSS items arrive over three unrelated protocols and
converge on `SourceItemBase`. Generation never learns which adapter produced
one — it passes `kind` to `writer.agent.source_instruction`, which is the only
place the three are told apart once they are rows.

The seam is genuine rather than hypothetical: there really are three of them,
and they share nothing but their output type.
"""
