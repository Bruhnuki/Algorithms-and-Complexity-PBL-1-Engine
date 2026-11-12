"""Local-AI content generation for the Scrum game.

The model only PROPOSES content. Everything here is checked by the game's own rules before it can be used:
ScrumScript challenges are run through the real interpreter, scenarios are checked against authored Scrum principles,
and the trust numbers and answer order come from the game, never from the model. Nothing in this package can change
a run's state; it can only add validated items to a library that new runs freeze a copy of.
"""
