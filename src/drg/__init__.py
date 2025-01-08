"""Dynamic Resilient Grid (DRG).

AI-driven local electricity demand forecasting and electrification stress
analysis for UK urban distribution networks.

The package is organised as a set of composable stages:

``drg.data``          ingestion of Low Carbon London smart-meter data and
                      public context APIs (Carbon Intensity, weather)
``drg.features``      time / statistical / exogenous feature engineering
``drg.models``        baseline, gradient-boosted and deep-learning forecasters
``drg.stress``        percentile-based statistical stress detection
``drg.simulation``    EV and heat-pump electrification scenario simulation
``drg.analysis``      sensitivity / peak-amplification analytics
``drg.explain``       SHAP explainability
``drg.streaming``     near-real-time replay engine
``drg.api``           FastAPI decision-support service
``drg.dashboard``     Streamlit operator dashboard
"""

__version__ = "1.0.0"

__all__ = ["__version__"]
