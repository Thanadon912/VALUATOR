import allure

def valuator_test(epic: str, feature: str, story: str, priority: str, severity: str, layer: str, test_id: str):
    def decorator(func):
        allure.epic(epic)(func)
        allure.feature(feature)(func)
        allure.story(story)(func)
        allure.label("priority", priority)(func)
        allure.label("severity", severity)(func)
        allure.label("layer", layer)(func)
        allure.label("owner", "Thanadon")(func)
        allure.label("testId", test_id)(func)
        return func
    return decorator
