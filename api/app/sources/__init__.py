"""Four adapters, one shape.

Competitor posts, tweets, web pages and RSS items arrive over four unrelated
protocols and converge on `SourceItemBase`. Generation never learns which
adapter produced one - it passes `kind` to `writer.agent.source_instruction`,
which is the only place the four are told apart once they are rows.

The seam is genuine rather than hypothetical: there really are four of them,
and they share nothing but their output type.
"""
