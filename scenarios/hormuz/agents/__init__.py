"""
scenarios/hormuz/agents — BDI agent definitions for the Hormuz scenario.

All 18 actors use DefaultBDIAgent — beliefs, desires, and capabilities are
declared in the SimSpec and hydrated by SimRunner.from_spec(). Custom subclasses
are not needed for this scenario: the theory cascade (Richardson, Fearon,
Wittman-Zartman) handles the strategic dynamics; agents contribute environmental
deltas based on their desires and capabilities.

Actor roster:
  State actors (military/political):
    iran, us, saudi_arabia, uae, qatar, kuwait, united_kingdom, russia, china

  Economic/import actors:
    japan, south_korea, india, opec

  Commercial actors:
    oil_majors, tanker_operators, marine_insurers, commodity_traders,
    shipping_logistics
"""
