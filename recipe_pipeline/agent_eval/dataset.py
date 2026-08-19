"""Frozen, constraint-annotated Agent evaluation scenarios for Step 17K."""

from __future__ import annotations

from collections.abc import Iterable

from recipe_pipeline.agent_eval.models import (
    EvaluationDataset,
    EvaluationScenario,
    EvaluationTurn,
    ExpectedBehavior,
)


DEMO_IMAGE_URL = (
    "https://aisearch.cdn.bcebos.com/pic_create/2026-04-10/10/"
    "74d52055e4947f8c.jpg"
)
IMAGE_REFERENCE = "74d52055e4947f8c.jpg"


def _expected(
    ingredients: Iterable[str] = (),
    *,
    recipe: bool = True,
    recipe_may: bool = False,
    web: bool = False,
    forbidden: Iterable[str] = (),
    allergens: Iterable[str] = (),
    diets: Iterable[str] = (),
    preferences: Iterable[str] = (),
    max_time: int | None = None,
    available_equipment: Iterable[str] = (),
    unavailable_equipment: Iterable[str] = (),
    visible: Iterable[str] = (),
    multiple: bool = False,
    current: bool = False,
) -> ExpectedBehavior:
    return ExpectedBehavior(
        recipe_kb_should_be_used=recipe,
        recipe_kb_may_be_used=recipe_may,
        web_should_be_used=web,
        required_ingredients=tuple(ingredients),
        forbidden_ingredients=tuple(forbidden),
        excluded_allergens=tuple(allergens),
        dietary_constraints=tuple(diets),
        soft_preferences=tuple(preferences),
        max_time_minutes=max_time,
        available_equipment=tuple(available_equipment),
        unavailable_equipment=tuple(unavailable_equipment),
        visible_ingredients=tuple(visible),
        request_multiple=multiple,
        explicit_current_web=current,
    )


def build_evaluation_dataset() -> EvaluationDataset:
    """Build exactly 100 stable scenarios; IDs and split never depend on RNG."""

    rows: list[tuple[str, str, tuple[EvaluationTurn, ...], tuple[str, ...], str | None]] = []

    ingredient_cases = [
        ("我有鸡蛋、西红柿和青椒，推荐几个简单的菜。", ("鸡蛋", "番茄", "青椒")),
        ("鸡蛋和菠菜能做什么？", ("鸡蛋", "菠菜")),
        ("家里有豆腐、蘑菇和小白菜，晚饭做什么？", ("豆腐", "蘑菇", "小白菜")),
        ("牛肉和西兰花怎么搭配做菜？", ("牛肉", "西兰花")),
        ("虾仁、豌豆、胡萝卜可以做什么？", ("虾仁", "豌豆", "胡萝卜")),
        ("用茄子和土豆推荐两道家常菜。", ("茄子", "土豆")),
        ("冰箱有鸡腿、香菇和青菜。", ("鸡腿", "香菇", "青菜")),
        ("三文鱼和芦笋有什么简单做法？", ("三文鱼", "芦笋")),
        ("南瓜、玉米和排骨能一起做什么？", ("南瓜", "玉米", "排骨")),
        ("我有米饭、鸡蛋、胡萝卜，想清库存。", ("米饭", "鸡蛋", "胡萝卜")),
        ("白菜和粉丝有哪些家常做法？", ("白菜", "粉丝")),
        ("鸡胸肉、黄瓜和木耳推荐三道菜。", ("鸡胸肉", "黄瓜", "木耳")),
        ("莲藕和猪肉怎么做比较好吃？", ("莲藕", "猪肉")),
        ("山药、胡萝卜、香菇能做什么？", ("山药", "胡萝卜", "香菇")),
        ("鳕鱼和番茄有什么搭配？", ("鳕鱼", "番茄")),
        ("西葫芦和鸡蛋推荐两种不同做法。", ("西葫芦", "鸡蛋")),
    ]
    for query, ingredients in ingredient_cases:
        rows.append(("ingredient_recommendation", "zh", (EvaluationTurn(query=query, expected=_expected(ingredients, multiple="几个" in query or "两" in query or "三" in query)),), (), None))

    partial_cases = [
        ("我只有鸡胸肉、土豆和洋葱。", ("鸡胸肉", "土豆", "洋葱")),
        ("只有豆腐和番茄，尽量别让我再买很多东西。", ("豆腐", "番茄")),
        ("手边只有面条、鸡蛋和葱。", ("面条", "鸡蛋", "葱")),
        ("我只有米饭和一根胡萝卜，能做什么？", ("米饭", "胡萝卜")),
        ("只有土豆、青椒，调料算齐全。", ("土豆", "青椒")),
        ("冰箱快空了，只有白菜和豆腐。", ("白菜", "豆腐")),
        ("只有燕麦、香蕉和牛奶，做个早餐。", ("燕麦", "香蕉", "牛奶")),
        ("我只有鸡蛋和虾仁，推荐少补材料的菜。", ("鸡蛋", "虾仁")),
        ("只有茄子、蒜和米饭，晚饭怎么解决？", ("茄子", "蒜", "米饭")),
        ("家里只剩蘑菇、洋葱和意面。", ("蘑菇", "洋葱", "意面")),
    ]
    for query, ingredients in partial_cases:
        rows.append(("partial_ingredient_coverage", "zh", (EvaluationTurn(query=query, expected=_expected(ingredients)),), (), None))

    multilingual_cases = [
        ("我有西红柿和egg。", ("番茄", "鸡蛋"), "mixed"),
        ("quick dinner with tofu and mushrooms", ("tofu", "mushroom"), "en"),
        ("potato 和鸡胸肉能做什么？", ("potato", "鸡胸肉"), "mixed"),
        ("番茄和tomato其实是同一种，配鸡蛋推荐菜。", ("番茄", "鸡蛋"), "mixed"),
        ("aubergine with minced pork recipe", ("eggplant", "pork"), "en"),
        ("青椒、bell pepper和beef怎么做？", ("bell pepper", "beef"), "mixed"),
        ("Give me two dishes with prawns and broccoli.", ("shrimp", "broccoli"), "en"),
        ("豆腐皮和tofu有什么家常搭配？", ("tofu",), "mixed"),
        ("courgette and egg for a simple lunch", ("zucchini", "egg"), "en"),
        ("I have scallion, rice and 鸡蛋.", ("scallion", "rice", "鸡蛋"), "mixed"),
    ]
    for query, ingredients, language in multilingual_cases:
        rows.append(("synonym_multilingual", language, (EvaluationTurn(query=query, expected=_expected(ingredients, multiple="two" in query.lower())),), (), None))

    preference_cases = [
        ("鸡肉怎么做？少油，不要辣。", ("鸡肉",), ("LOW_OIL", "NON_SPICY")),
        ("豆腐蘑菇，想吃清淡一点。", ("豆腐", "蘑菇"), ("LIGHT",)),
        ("牛肉做一道高蛋白、少油的菜。", ("牛肉",), ("HIGH_PROTEIN", "LOW_OIL")),
        ("茄子怎么做不油腻？", ("茄子",), ("LOW_OIL",)),
        ("鸡蛋番茄不要太甜也不要辣。", ("鸡蛋", "番茄"), ("NON_SPICY", "LOW_SWEET")),
        ("想用鱼做清淡晚饭，少盐。", ("鱼",), ("LIGHT", "LOW_SALT")),
        ("土豆和西兰花，做得脆一点。", ("土豆", "西兰花"), ("CRISPY",)),
        ("虾仁做一道酸甜但不辣的菜。", ("虾仁",), ("SWEET_SOUR", "NON_SPICY")),
        ("鸡胸肉想要嫩一点，别太油。", ("鸡胸肉",), ("TENDER", "LOW_OIL")),
        ("南瓜做健康一点的主食。", ("南瓜",), ("HEALTHY",)),
    ]
    for query, ingredients, preferences in preference_cases:
        rows.append(("preference_constraints", "zh", (EvaluationTurn(query=query, expected=_expected(ingredients, preferences=preferences)),), (), None))

    dietary_cases = [
        ("鸡胸肉配蔬菜，不要花生。", ("鸡胸肉",), ("花生",), (), ()),
        ("推荐三道素食晚餐。", (), (), (), ("VEGETARIAN",)),
        ("纯素早餐，不要牛奶和鸡蛋。", (), ("牛奶", "鸡蛋"), ("MILK", "EGG"), ("VEGAN",)),
        ("海鲜过敏，推荐一道鸡肉菜。", ("鸡肉",), (), ("FISH", "SHELLFISH"), ()),
        ("芝麻过敏，豆腐怎么做？", ("豆腐",), ("芝麻",), ("SESAME",), ()),
        ("不要坚果，燕麦早餐怎么做？", ("燕麦",), ("坚果",), ("TREE_NUT", "PEANUT"), ()),
        ("无麸质晚饭，用土豆和牛肉。", ("土豆", "牛肉"), (), ("WHEAT",), ()),
        ("蛋奶素，想吃蘑菇意面。", ("蘑菇", "意面"), (), (), ("VEGETARIAN",)),
        ("不吃猪肉，推荐牛肉家常菜。", ("牛肉",), ("猪肉",), (), ()),
        ("乳糖不耐受，南瓜浓汤不要奶制品。", ("南瓜",), ("牛奶", "奶油"), ("MILK",), ()),
    ]
    for query, ingredients, forbidden, allergens, diets in dietary_cases:
        rows.append(("dietary_restrictions", "zh", (EvaluationTurn(query=query, expected=_expected(ingredients, forbidden=forbidden, allergens=allergens, diets=diets, multiple="三道" in query)),), (), None))

    time_cases = [
        ("鸡蛋番茄，20分钟以内。", ("鸡蛋", "番茄"), 20),
        ("15分钟做完的豆腐菜。", ("豆腐",), 15),
        ("下班很晚，10分钟内用面条做晚饭。", ("面条",), 10),
        ("鸡胸肉和西兰花，30分钟以内。", ("鸡胸肉", "西兰花"), 30),
        ("25分钟能完成的三文鱼做法。", ("三文鱼",), 25),
        ("早餐只有12分钟，鸡蛋和吐司。", ("鸡蛋", "吐司"), 12),
        ("40分钟内做一锅排骨土豆。", ("排骨", "土豆"), 40),
        ("快速素食晚饭，最多20分钟。", (), 20),
    ]
    for query, ingredients, minutes in time_cases:
        rows.append(("time_constraints", "zh", (EvaluationTurn(query=query, expected=_expected(ingredients, max_time=minutes)),), (), None))

    equipment_cases = [
        ("只有空气炸锅，用鸡翅做什么？", ("鸡翅",), ("AIR_FRYER",), ()),
        ("没有烤箱，土豆怎么做？", ("土豆",), (), ("OVEN",)),
        ("宿舍只有电饭锅，推荐一锅饭。", ("米饭",), ("RICE_COOKER",), ()),
        ("只有微波炉和一个碗，鸡蛋怎么做？", ("鸡蛋",), ("MICROWAVE",), ()),
        ("没有炒锅，用蒸锅做鱼。", ("鱼",), ("STEAMER",), ("WOK",)),
        ("只有平底锅，不能用烤箱，鸡胸肉怎么做？", ("鸡胸肉",), ("PAN",), ("OVEN",)),
    ]
    for query, ingredients, available, unavailable in equipment_cases:
        rows.append(("equipment_constraints", "zh", (EvaluationTurn(query=query, expected=_expected(ingredients, available_equipment=available, unavailable_equipment=unavailable)),), (), None))

    combination_cases = [
        ("鸡肉、土豆，少油，不辣，30分钟以内。", ("鸡肉", "土豆"), (), (), ("LOW_OIL", "NON_SPICY"), 30, ()),
        ("豆腐蘑菇纯素，不要花生，20分钟内。", ("豆腐", "蘑菇"), ("花生",), ("VEGAN",), ("QUICK",), 20, ()),
        ("牛肉西兰花，少盐，25分钟，不用烤箱。", ("牛肉", "西兰花"), (), (), ("LOW_SALT",), 25, ("OVEN",)),
        ("鸡蛋番茄，不辣、低油，15分钟。", ("鸡蛋", "番茄"), (), (), ("LOW_OIL", "NON_SPICY"), 15, ()),
        ("空气炸锅鸡翅，不要蜂蜜，40分钟内。", ("鸡翅",), ("蜂蜜",), (), ("NON_SWEET",), 40, ("OVEN", "STOVE")),
        ("素食、无坚果，用南瓜和豆腐做晚饭。", ("南瓜", "豆腐"), ("坚果",), ("VEGETARIAN",), (), None, ()),
        ("虾仁和蔬菜，少油不辣，最多20分钟。", ("虾仁",), (), (), ("LOW_OIL", "NON_SPICY"), 20, ()),
        ("只有电饭锅，鸡肉和米饭，30分钟，少油。", ("鸡肉", "米饭"), (), (), ("LOW_OIL",), 30, ("OVEN",)),
        ("三文鱼芦笋，无奶，25分钟内，不用烤箱。", ("三文鱼", "芦笋"), ("牛奶", "奶油"), (), (), 25, ("OVEN",)),
        ("茄子土豆，不吃猪肉，不辣，30分钟。", ("茄子", "土豆"), ("猪肉",), (), ("NON_SPICY",), 30, ()),
    ]
    for query, ingredients, forbidden, diets, preferences, minutes, unavailable in combination_cases:
        rows.append(("combination_constraints", "zh", (EvaluationTurn(query=query, expected=_expected(ingredients, forbidden=forbidden, diets=diets, preferences=preferences, max_time=minutes, unavailable_equipment=unavailable)),), (), None))

    follow_up_cases = [
        (("我有鸡蛋、西红柿和青椒，推荐三道菜。", "详细说一下第二道菜怎么做。", "能少放点油吗？"), ("鸡蛋", "番茄", "青椒")),
        (("豆腐和蘑菇推荐两道不辣的菜。", "第一道需要哪些调料？", "没有生抽，能替换吗？"), ("豆腐", "蘑菇")),
        (("鸡胸肉土豆，30分钟内推荐两个方案。", "第二个方案具体怎么做？", "份量改成两个人。"), ("鸡胸肉", "土豆")),
        (("给我三道素食晚餐。", "展开讲第二道。", "记得不要放香菜。"), ()),
        (("虾仁和西兰花推荐两道菜。", "哪道更快？", "那就讲快的那道步骤。"), ("虾仁", "西兰花")),
        (("只有空气炸锅和鸡翅，给两个做法。", "第二个会辣吗？", "改成完全不辣。"), ("鸡翅",)),
    ]
    for queries, ingredients in follow_up_cases:
        turns = []
        for index, query in enumerate(queries):
            turns.append(EvaluationTurn(
                query=query,
                expected=_expected(
                    ingredients if index == 0 else (),
                    recipe=index == 0,
                    recipe_may=index > 0,
                    preferences=("LOW_OIL",) if "少放点油" in query else (),
                    forbidden=("香菜",) if "香菜" in query else (),
                    multiple=index == 0,
                ),
            ))
        rows.append(("follow_up_context", "zh", tuple(turns), (), None))

    current_cases = [
        "最近网上流行什么鸡蛋做法？",
        "Find current viral tofu recipes and give web sources.",
        "今年网上热门的空气炸锅土豆做法有哪些？",
        "查一下当前网页上流行的低油晚餐趋势。",
    ]
    for query in current_cases:
        rows.append(("explicit_current_web", "en" if query.startswith("Find") else "zh", (EvaluationTurn(query=query, expected=_expected(recipe=False, recipe_may=True, web=True, current=True, multiple=True)),), (), None))

    gap_cases = [
        "推荐一道正宗的冰岛发酵鲨鱼 Hákarl 做法。",
        "How do I make molecular-gastronomy olive oil spheres at home?",
        "想做秘鲁 pachamanca，给我传统做法。",
        "推荐一道用非洲猴面包树叶粉做的传统汤。",
    ]
    for query in gap_cases:
        rows.append(("kb_coverage_gap", "en" if query.startswith("How") else "zh", (EvaluationTurn(query=query, expected=_expected(recipe=True, web=True)),), (), None))

    image_queries = [
        "看看图片里有哪些主要蔬菜，并推荐三道能尽量利用它们的菜。",
        "根据这张冰箱照片推荐一顿少油、不辣的晚饭。",
        "Identify the visible vegetables, then suggest two practical recipes.",
    ]
    for query in image_queries:
        rows.append(("image_ingredient_query", "en" if query.startswith("Identify") else "zh", (EvaluationTurn(query=query, expected=_expected(("番茄", "青椒", "茄子", "青菜"), preferences=("LOW_OIL", "NON_SPICY") if "少油" in query else (), visible=("番茄", "青椒", "茄子", "青菜"), multiple=True)),), (), DEMO_IMAGE_URL))

    memory_cases = [
        ("给我推荐晚饭。", ("avoid coriander", "prefer low oil"), ("香菜",), ("LOW_OIL",)),
        ("推荐三道适合我的家常菜。", ("vegetarian", "allergic to peanuts"), ("花生",), ("VEGETARIAN",)),
        ("今天吃什么？", ("do not eat pork", "prefer non-spicy food"), ("猪肉",), ("NON_SPICY",)),
    ]
    for query, memories, forbidden, preferences in memory_cases:
        diets = ("VEGETARIAN",) if "vegetarian" in memories else ()
        allergens = ("PEANUT",) if "allergic to peanuts" in memories else ()
        rows.append(("long_term_memory", "zh", (EvaluationTurn(query=query, expected=_expected(forbidden=forbidden, allergens=allergens, diets=diets, preferences=preferences, multiple="三道" in query)),), memories, None))

    if len(rows) != 100:
        raise AssertionError(f"evaluation dataset must contain 100 rows, got {len(rows)}")

    scenarios = []
    for index, (category, language, turns, memories, image_url) in enumerate(rows, 1):
        scenarios.append(EvaluationScenario(
            scenario_id=f"ARAG-{index:03d}",
            category=category,
            split="development" if index % 5 == 1 else "holdout",
            language=language,
            turns=turns,
            user_memories=memories,
            image_url=image_url,
            image_reference=IMAGE_REFERENCE if image_url else None,
        ))
    return EvaluationDataset(scenarios=tuple(scenarios))
