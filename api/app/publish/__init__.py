"""Getting a finished Draft out of this machine.

Two steps, in two modules, because they fail for unrelated reasons: `storage`
puts the picture somewhere the internet can read it, and `metricool` hands
Metricool the words and a link to that picture.

The order is forced. Metricool's post body carries an image **URL**, not image
bytes — there is no upload endpoint, verified against both their documentation
and the old system, which never used one either. Facebook then fetches that URL
when the post goes out, which is why the link has to outlive the API call.
"""
