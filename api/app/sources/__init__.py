"""Three adapters, one shape.

Competitor posts, tweets and RSS items arrive over three unrelated protocols and
converge on `SourceItemBase`. Generation never learns which adapter produced
one — it asks `kind.is_factual`, which is what decides whether the subject binds
the writer.

The seam is genuine rather than hypothetical: there really are three of them,
and they share nothing but their output type.
"""
