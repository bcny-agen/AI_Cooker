"""Fixed user-style retrieval test set; recipes are never changed to fit it."""

from __future__ import annotations

from recipe_pipeline.evaluation.models import EvaluationQuery, QueryKind


def _query(
    query_id: str,
    kind: QueryKind,
    text: str,
    *expected_names: str,
) -> EvaluationQuery:
    return EvaluationQuery(
        query_id=query_id,
        query=text,
        kind=kind,
        expected_recipe_names=list(expected_names),
    )


EVALUATION_QUERIES: tuple[EvaluationQuery, ...] = (
    _query("ingredient-01", QueryKind.INGREDIENT, "我有鸡蛋和番茄，可以做什么？", "番茄鸡蛋豆腐煲", "番茄洋葱炒鸡蛋", "菜花番茄炒鸡蛋", "番茄鸡蛋面"),
    _query("ingredient-02", QueryKind.INGREDIENT, "chicken and potato recipes", "豆角土豆炖鸡肉"),
    _query("ingredient-03", QueryKind.INGREDIENT, "牛肉和芹菜能做什么", "芹菜炒牛肉", "芹菜胡萝卜炒牛肉"),
    _query("ingredient-04", QueryKind.INGREDIENT, "豆腐 菠菜", "菠菜豆腐汤", "菠菜毛豆豆腐煮"),
    _query("ingredient-05", QueryKind.INGREDIENT, "虾仁 西兰花", "西兰花炒虾仁"),
    _query("ingredient-06", QueryKind.INGREDIENT, "egg cucumber recipe", "黄瓜炒鸡蛋", "黄瓜鸡蛋汤", "黄瓜鸡蛋炒饭"),
    _query("ingredient-07", QueryKind.INGREDIENT, "茄子和豆腐", "茄子番茄烧豆腐"),
    _query("ingredient-08", QueryKind.INGREDIENT, "玉米 鸡肉", "玉米胡萝卜鸡肉汤", "山药玉米鸡肉汤"),
    _query("ingredient-09", QueryKind.INGREDIENT, "香菇鸡肉家常菜", "香菇蒸鸡肉", "白萝卜香菇炖鸡肉"),
    _query("ingredient-10", QueryKind.INGREDIENT, "napa cabbage tofu", "白菜炖豆腐", "白菜香菇豆腐汤", "白菜豆腐家常煮"),
    _query("ingredient-11", QueryKind.INGREDIENT, "salmon pumpkin", "三文鱼南瓜烤盘"),
    _query("ingredient-12", QueryKind.INGREDIENT, "燕麦 香蕉", "香蕉燕麦酸奶杯", "牛奶香蕉燕麦粥", "香蕉鸡蛋燕麦饼"),
    _query("ingredient-13", QueryKind.INGREDIENT, "莲藕 胡萝卜", "莲藕胡萝卜炖猪肉"),
    _query("ingredient-14", QueryKind.INGREDIENT, "冬瓜虾仁", "冬瓜虾仁汤"),
    _query("ingredient-15", QueryKind.INGREDIENT, "potato onion", "土豆洋葱鸡蛋饼", "洋葱土豆煎饼"),
    _query("ingredient-16", QueryKind.INGREDIENT, "豆腐 香菇 芹菜", "芹菜香菇炒豆腐"),
    _query("ingredient-17", QueryKind.INGREDIENT, "beef broccoli", "西兰花胡萝卜炒牛肉"),
    _query("ingredient-18", QueryKind.INGREDIENT, "紫菜 鸡蛋", "紫菜鸡蛋汤", "紫菜鸡蛋面"),
    _query("ingredient-19", QueryKind.INGREDIENT, "红薯 酸奶", "红薯酸奶燕麦碗"),
    _query("ingredient-20", QueryKind.INGREDIENT, "chickpea cauliflower", "菜花鹰嘴豆煮"),
    _query("ingredient-21", QueryKind.INGREDIENT, "white radish fish", "白萝卜鱼汤"),
    _query("ingredient-22", QueryKind.INGREDIENT, "玉米 鸡蛋 面粉", "玉米鸡蛋早餐饼"),
    _query("ingredient-23", QueryKind.INGREDIENT, "peas rice shrimp", "豌豆虾仁炒饭"),
    _query("ingredient-24", QueryKind.INGREDIENT, "豆腐和番茄", "番茄鸡蛋豆腐煲", "番茄豆腐快煮汤", "茄子番茄烧豆腐"),
    _query("ingredient-25", QueryKind.INGREDIENT, "山药鸡肉", "山药胡萝卜鸡汤", "山药玉米鸡肉汤"),
    _query("synonym-01", QueryKind.SYNONYM, "西红柿鸡蛋", "番茄鸡蛋豆腐煲", "番茄洋葱炒鸡蛋", "菜花番茄炒鸡蛋", "番茄鸡蛋面"),
    _query("synonym-02", QueryKind.SYNONYM, "番茄炒蛋", "番茄洋葱炒鸡蛋", "菜花番茄炒鸡蛋"),
    _query("synonym-03", QueryKind.SYNONYM, "tomato egg dish", "番茄鸡蛋豆腐煲", "番茄洋葱炒鸡蛋", "菜花番茄炒鸡蛋", "番茄鸡蛋面"),
    _query("synonym-04", QueryKind.SYNONYM, "potato chicken stew", "豆角土豆炖鸡肉"),
    _query("synonym-05", QueryKind.SYNONYM, "aubergine tofu", "茄子番茄烧豆腐"),
    _query("synonym-06", QueryKind.SYNONYM, "broccoli shrimp", "西兰花炒虾仁"),
    _query("synonym-07", QueryKind.SYNONYM, "eggplant green beans", "茄子烧豆角"),
    _query("synonym-08", QueryKind.SYNONYM, "salmon lemon", "三文鱼南瓜烤盘", "空气炸锅柠檬三文鱼"),
    _query("synonym-09", QueryKind.SYNONYM, "tofu napa cabbage", "白菜炖豆腐", "白菜香菇豆腐汤", "白菜豆腐家常煮"),
    _query("synonym-10", QueryKind.SYNONYM, "sweet potato yogurt", "红薯酸奶燕麦碗"),
    _query("scenario-01", QueryKind.SCENARIO, "10分钟早餐", "香蕉燕麦酸奶杯", "苹果酸奶燕麦杯"),
    _query("scenario-02", QueryKind.SCENARIO, "20分钟能做好的晚饭", "洋葱鸡蛋炒饭", "青椒鸡肉快炒", "豆芽鸡蛋快炒", "西兰花鸡蛋快炒", "黄瓜鸡蛋炒饭"),
    _query("scenario-03", QueryKind.SCENARIO, "适合完全新手的菜", "番茄洋葱炒鸡蛋", "鸡蛋蒸豆腐", "黄瓜鸡蛋汤", "白菜豆腐家常煮", "玉米胡萝卜炒鸡蛋"),
    _query("scenario-04", QueryKind.SCENARIO, "空气炸锅食谱", "空气炸锅蜜汁鸡翅", "空气炸锅黑椒土豆角", "空气炸锅柠檬三文鱼", "空气炸锅蒜香西兰花", "空气炸锅椒盐南瓜"),
    _query("scenario-05", QueryKind.SCENARIO, "一家人吃的家常晚餐", "青椒炒猪肉", "芹菜炒牛肉", "土豆烧鸡腿", "白菜炖豆腐", "胡萝卜土豆炖牛肉"),
    _query("scenario-06", QueryKind.SCENARIO, "healthy meal ideas", "西兰花清炒鸡肉", "三文鱼南瓜烤盘", "鹰嘴豆黄瓜番茄沙拉", "菠菜毛豆豆腐煮", "冬瓜鸡肉清汤"),
    _query("scenario-07", QueryKind.SCENARIO, "学生快手饭", "洋葱鸡蛋炒饭", "胡萝卜鸡肉炒饭", "豌豆虾仁炒饭", "毛豆胡萝卜炒饭", "黄瓜鸡蛋炒饭"),
    _query("scenario-08", QueryKind.SCENARIO, "新手也能做的蒸菜", "鸡蛋蒸豆腐", "玉米鸡蛋早餐杯"),
    _query("scenario-09", QueryKind.SCENARIO, "30分钟以内的汤", "菠菜豆腐汤", "紫菜鸡蛋汤", "番茄豆腐快煮汤", "黄瓜鸡蛋汤", "菠菜鸡蛋汤"),
    _query("scenario-10", QueryKind.SCENARIO, "quick noodle meal", "番茄鸡蛋面", "菠菜鸡蛋面", "紫菜鸡蛋面", "番茄虾仁面"),
    _query("preference-01", QueryKind.PREFERENCE, "少油的家常菜", "菠菜豆腐汤", "香菇西兰花蒸豆腐", "鸡蛋蒸豆腐", "鹰嘴豆黄瓜番茄沙拉", "苹果酸奶燕麦杯"),
    _query("preference-02", QueryKind.PREFERENCE, "我不吃辣", "白菜炖豆腐", "冬瓜虾仁汤", "菠菜豆腐汤", "紫菜鸡蛋汤", "海带豆腐汤"),
    _query("preference-03", QueryKind.PREFERENCE, "高蛋白晚餐", "青椒炒猪肉", "芹菜炒牛肉", "香菇蒸鸡肉", "西兰花炒虾仁", "白萝卜鱼汤"),
    _query("preference-04", QueryKind.PREFERENCE, "素食豆腐料理", "白菜炖豆腐", "菠菜豆腐汤", "香菇白菜炒豆腐", "芹菜香菇炒豆腐", "南瓜烧豆腐"),
    _query("preference-05", QueryKind.PREFERENCE, "vegan quick meal", "黄瓜豆腐拌饭", "番茄豆腐快煮汤"),
    _query("preference-06", QueryKind.PREFERENCE, "少油鸡肉", "香菇蒸鸡肉", "冬瓜鸡肉清汤", "山药胡萝卜鸡汤", "山药玉米鸡肉汤"),
    _query("preference-07", QueryKind.PREFERENCE, "清淡的鱼", "白萝卜鱼汤", "三文鱼南瓜烤盘"),
    _query("preference-08", QueryKind.PREFERENCE, "不辣的空气炸锅菜", "空气炸锅黑椒土豆角", "空气炸锅柠檬三文鱼", "空气炸锅蒜香西兰花", "空气炸锅椒盐南瓜", "空气炸锅红薯条"),
    _query("preference-09", QueryKind.PREFERENCE, "高蛋白鸡蛋早餐", "玉米鸡蛋早餐饼", "香蕉鸡蛋燕麦饼", "玉米鸡蛋早餐杯", "菠菜奶酪煎蛋"),
    _query("preference-10", QueryKind.PREFERENCE, "vegetarian healthy meal", "鹰嘴豆黄瓜番茄沙拉", "菠菜毛豆豆腐煮", "香菇西兰花蒸豆腐", "苹果酸奶燕麦杯", "菜花鹰嘴豆煮"),
    _query("combined-01", QueryKind.COMBINED, "新手做鸡蛋番茄", "番茄洋葱炒鸡蛋"),
    _query("combined-02", QueryKind.COMBINED, "空气炸锅土豆", "空气炸锅黑椒土豆角"),
    _query("combined-03", QueryKind.COMBINED, "20分钟豆腐料理", "番茄豆腐快煮汤", "黄瓜豆腐拌饭"),
    _query("combined-04", QueryKind.COMBINED, "少油白菜豆腐", "白菜炖豆腐", "白菜香菇豆腐汤", "白菜豆腐家常煮"),
    _query("combined-05", QueryKind.COMBINED, "healthy shrimp zucchini", "西葫芦虾仁快炒"),
)


def get_evaluation_queries() -> list[EvaluationQuery]:
    return list(EVALUATION_QUERIES)
