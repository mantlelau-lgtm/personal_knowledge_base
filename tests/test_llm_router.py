from common.llm_router import ModelRouter


def test_model_router_pick(settings):
    settings.llm_model_light = "light-model"
    settings.llm_model_default = "default-model"
    settings.llm_model_heavy = "heavy-model"
    router = ModelRouter(settings)
    assert router.pick("summarize") == "light-model"
    assert router.pick("extract") == "light-model"
    assert router.pick("chat") == "default-model"
    assert router.pick("query_rewrite") == "default-model"
    assert router.pick("iterative") == "heavy-model"
    assert router.pick("complex") == "heavy-model"


def test_model_router_fallback_to_llm_model(settings):
    settings.llm_model_light = ""
    settings.llm_model_default = ""
    settings.llm_model_heavy = ""
    settings.llm_model = "single-model"
    router = ModelRouter(settings)
    assert router.pick("summarize") == "single-model"
    assert router.pick("chat") == "single-model"
    assert router.pick("iterative") == "single-model"


def test_model_router_describe(settings):
    settings.llm_model_light = "L"
    settings.llm_model_default = "D"
    settings.llm_model_heavy = "H"
    desc = ModelRouter(settings).describe()
    assert desc == {"light": "L", "default": "D", "heavy": "H"}
