"""Codex-authored canonical recipe blueprints for Golden Dataset v1."""

from __future__ import annotations

from recipe_pipeline.golden.models import GoldenBlueprint, PrimaryCollection
from recipe_pipeline.schemas.recipe import CookingMethod, Cuisine, RecipeCategory, Region


def _blueprint(
    name: str,
    ingredients: tuple[str, ...],
    method: CookingMethod,
    category: RecipeCategory,
    minutes: int,
    collection: PrimaryCollection,
    style: str,
) -> GoldenBlueprint:
    return GoldenBlueprint(
        name=name,
        collection=collection,
        style=style,
        ingredients=ingredients,
        method=method,
        category=category,
        total_minutes=minutes,
    )


def _rows(
    rows: tuple[tuple[str, tuple[str, ...]], ...],
    *,
    method: CookingMethod,
    category: RecipeCategory,
    minutes: int,
    collection: PrimaryCollection,
    style: str,
) -> list[GoldenBlueprint]:
    return [
        _blueprint(name, ingredients, method, category, minutes, collection, style)
        for name, ingredients in rows
    ]


_CHINESE_FAMOUS = (
    ("麻婆豆腐", ("豆腐", "猪肉", "豆瓣酱", "花椒")),
    ("宫保鸡丁", ("鸡肉", "花生", "辣椒", "醋")),
    ("鱼香肉丝", ("猪肉", "木耳", "胡萝卜", "豆瓣酱", "醋")),
    ("回锅肉", ("五花肉", "青椒", "豆瓣酱")),
    ("水煮牛肉", ("牛肉", "豆芽", "豆瓣酱", "花椒", "辣椒", "水")),
    ("水煮鱼", ("草鱼", "豆芽", "豆瓣酱", "花椒", "辣椒", "水")),
    ("酸菜鱼", ("草鱼", "酸菜", "辣椒", "水")),
    ("辣子鸡", ("鸡肉", "辣椒", "花椒")),
    ("口水鸡", ("整鸡", "辣椒", "花椒", "芝麻")),
    ("蒜泥白肉", ("五花肉", "大蒜", "辣椒", "醋")),
    ("干煸四季豆", ("豆角", "猪肉", "辣椒")),
    ("鱼香茄子", ("茄子", "猪肉", "豆瓣酱", "醋")),
    ("地三鲜", ("土豆", "茄子", "青椒")),
    ("东坡肉", ("五花肉", "生抽", "老抽", "冰糖")),
    ("糖醋排骨", ("猪排骨", "醋", "白糖")),
    ("红烧排骨", ("猪排骨", "生抽", "老抽", "八角")),
    ("家常红烧肉", ("五花肉", "生抽", "老抽", "八角")),
    ("木须肉", ("猪肉", "鸡蛋", "木耳", "黄瓜")),
    ("京酱肉丝", ("猪肉", "甜面酱", "小葱", "豆皮")),
    ("葱爆羊肉", ("羊肉", "小葱", "生抽")),
    ("孜然羊肉", ("羊肉", "孜然", "洋葱")),
    ("红烧狮子头", ("肉馅", "马蹄", "生抽", "水")),
    ("小鸡炖蘑菇", ("整鸡", "香菇", "水")),
    ("猪肉炖粉条", ("五花肉", "粉丝", "白菜", "水")),
    ("锅包肉", ("猪肉", "淀粉", "醋", "白糖")),
    ("油焖大虾", ("虾", "番茄酱", "生抽")),
    ("西湖醋鱼", ("草鱼", "醋", "白糖", "水")),
    ("油焖春笋", ("春笋", "生抽", "白糖")),
    ("雪菜烧鱼", ("鱼", "雪菜", "水")),
    ("白切鸡", ("整鸡", "姜", "小葱", "水")),
    ("豉油鸡", ("整鸡", "生抽", "姜", "水")),
    ("豉汁蒸排骨", ("猪排骨", "豆豉", "大蒜")),
    ("蜜汁叉烧", ("五花肉", "蜂蜜", "生抽")),
    ("菠萝咕噜肉", ("猪肉", "菠萝", "番茄酱", "醋")),
    ("蚝油牛肉", ("牛肉", "蚝油", "青椒")),
    ("滑蛋虾仁", ("虾", "鸡蛋", "小葱")),
    ("清蒸鲈鱼", ("鲈鱼", "姜", "小葱")),
    ("砂锅豆腐", ("豆腐", "白菜", "香菇", "水")),
    ("肉末粉丝煲", ("肉馅", "粉丝", "豆瓣酱", "水")),
    ("干锅花菜", ("菜花", "五花肉", "辣椒")),
)


_CHINESE_STIR_PAIRS = (
    ("芹菜炒牛肉", ("芹菜", "牛肉")), ("芹菜炒猪肉", ("芹菜", "猪肉")),
    ("西兰花炒牛肉", ("西兰花", "牛肉")), ("西兰花炒虾仁", ("西兰花", "虾")),
    ("荷兰豆炒牛肉", ("荷兰豆", "牛肉")), ("荷兰豆炒虾仁", ("荷兰豆", "虾")),
    ("蒜薹炒猪肉", ("蒜薹", "猪肉")), ("蒜薹炒牛肉", ("蒜薹", "牛肉")),
    ("莴笋炒猪肉", ("莴笋", "猪肉")), ("莴笋炒鸡肉", ("莴笋", "鸡肉")),
    ("茭白炒猪肉", ("茭白", "猪肉")), ("苦瓜炒牛肉", ("苦瓜", "牛肉")),
    ("秋葵炒鸡肉", ("秋葵", "鸡肉")), ("秋葵炒虾仁", ("秋葵", "虾")),
    ("芦笋炒牛肉", ("芦笋", "牛肉")), ("芦笋炒虾仁", ("芦笋", "虾")),
    ("芦笋炒鸡肉", ("芦笋", "鸡肉")), ("木耳炒猪肉", ("木耳", "猪肉")),
    ("木耳炒鸡肉", ("木耳", "鸡肉")), ("杏鲍菇炒牛肉", ("杏鲍菇", "牛肉")),
    ("杏鲍菇炒鸡肉", ("杏鲍菇", "鸡肉")), ("平菇炒猪肉", ("平菇", "猪肉")),
    ("竹笋炒猪肉", ("竹笋", "猪肉")), ("竹笋炒鸡肉", ("竹笋", "鸡肉")),
    ("青椒炒牛肉", ("青椒", "牛肉")), ("青椒炒鸡肉", ("青椒", "鸡肉")),
    ("洋葱炒牛肉", ("洋葱", "牛肉")), ("洋葱炒鸡肉", ("洋葱", "鸡肉")),
    ("韭黄炒猪肉", ("韭黄", "猪肉")), ("韭黄炒虾仁", ("韭黄", "虾")),
    ("空心菜炒腐竹", ("空心菜", "腐竹")), ("芥蓝炒牛肉", ("芥蓝", "牛肉")),
    ("芥蓝炒虾仁", ("芥蓝", "虾")), ("菜花炒猪肉", ("菜花", "猪肉")),
    ("菜花炒牛肉", ("菜花", "牛肉")), ("莲藕炒猪肉", ("莲藕", "猪肉")),
    ("莲藕炒鸡肉", ("莲藕", "鸡肉")), ("丝瓜炒虾仁", ("丝瓜", "虾")),
    ("西葫芦炒虾仁", ("西葫芦", "虾")), ("油菜炒香菇", ("油菜", "香菇")),
    ("油菜炒豆皮", ("油菜", "豆皮")), ("白菜炒木耳", ("白菜", "木耳")),
    ("白菜炒肉片", ("白菜", "猪肉")), ("黄瓜炒肉片", ("黄瓜", "猪肉")),
    ("黄瓜炒虾仁", ("黄瓜", "虾")), ("豆角炒肉末", ("豆角", "肉馅")),
    ("豆角炒鸡丁", ("豆角", "鸡肉")), ("毛豆炒鸡丁", ("毛豆", "鸡肉")),
    ("毛豆炒肉末", ("毛豆", "肉馅")), ("豌豆炒虾仁", ("豌豆", "虾")),
    ("豌豆炒鸡丁", ("豌豆", "鸡肉")), ("酸豆角炒肉末", ("酸豆角", "肉馅")),
    ("榨菜炒肉丝", ("榨菜", "猪肉")), ("雪菜炒肉丝", ("雪菜", "猪肉")),
    ("雪菜炒毛豆", ("雪菜", "毛豆")), ("香菇炒鸡肉", ("香菇", "鸡肉")),
    ("香菇炒牛肉", ("香菇", "牛肉")), ("金针菇炒牛肉", ("金针菇", "牛肉")),
    ("平菇炒鸡肉", ("平菇", "鸡肉")), ("腐竹炒木耳", ("腐竹", "木耳")),
    ("腐竹炒芹菜", ("腐竹", "芹菜")), ("豆皮炒青椒", ("豆皮", "青椒")),
    ("莴笋炒木耳", ("莴笋", "木耳")), ("山药炒木耳", ("山药", "木耳")),
    ("山药炒荷兰豆", ("山药", "荷兰豆")), ("莲藕炒荷兰豆", ("莲藕", "荷兰豆")),
    ("土豆炒牛肉", ("土豆", "牛肉")), ("土豆炒鸡丁", ("土豆", "鸡肉")),
    ("胡萝卜炒牛肉", ("胡萝卜", "牛肉")), ("胡萝卜炒鸡肉", ("胡萝卜", "鸡肉")),
    ("洋葱炒猪肉", ("洋葱", "猪肉")), ("茄子炒肉末", ("茄子", "肉馅")),
    ("西葫芦炒肉片", ("西葫芦", "猪肉")), ("苦瓜炒肉片", ("苦瓜", "猪肉")),
    ("豆芽炒肉丝", ("豆芽", "猪肉")), ("豆芽炒鸡丝", ("豆芽", "鸡肉")),
    ("韭菜炒鱿鱼", ("韭菜", "鱿鱼")), ("青椒炒鱿鱼", ("青椒", "鱿鱼")),
    ("芹菜炒鱿鱼", ("芹菜", "鱿鱼")), ("荷兰豆炒鸡肉", ("荷兰豆", "鸡肉")),
)


_CHINESE_EGG = tuple(
    (f"{vegetable}炒鸡蛋", (vegetable, "鸡蛋"))
    for vegetable in (
        "黄瓜", "苦瓜", "韭菜", "韭黄", "丝瓜", "菠菜", "木耳", "西葫芦",
        "青椒", "洋葱", "毛豆", "豌豆", "蒜薹", "芦笋", "秋葵", "莴笋",
        "香菇", "平菇", "菜花", "豆芽",
    )
)


_CHINESE_TOFU = (
    ("白菜炖豆腐", ("白菜", "豆腐", "水")), ("家常烧豆腐", ("豆腐", "青椒", "木耳", "水")),
    ("香菇烧豆腐", ("香菇", "豆腐", "水")), ("番茄烧豆腐", ("番茄", "豆腐", "水")),
    ("茄子烧豆腐", ("茄子", "豆腐", "水")), ("芹菜炒豆腐", ("芹菜", "豆腐")),
    ("青椒炒豆腐", ("青椒", "豆腐")), ("木耳烧豆腐", ("木耳", "豆腐", "水")),
    ("金针菇豆腐煲", ("金针菇", "豆腐", "水")), ("丝瓜烧豆腐", ("丝瓜", "豆腐", "水")),
    ("苦瓜烧豆腐", ("苦瓜", "豆腐", "水")), ("西兰花烧豆腐", ("西兰花", "豆腐", "水")),
    ("莴笋烧豆腐", ("莴笋", "豆腐", "水")), ("豆角烧豆腐", ("豆角", "豆腐", "水")),
    ("南瓜烧豆腐", ("南瓜", "豆腐", "水")), ("雪菜豆腐", ("雪菜", "豆腐", "水")),
    ("酸菜豆腐", ("酸菜", "豆腐", "水")), ("虾仁豆腐", ("虾", "豆腐", "水")),
    ("肉末豆腐", ("肉馅", "豆腐", "水")), ("腐竹烧豆腐", ("腐竹", "豆腐", "水")),
)


_CHINESE_SOUPS = (
    ("番茄蛋花汤", ("番茄", "鸡蛋", "水")), ("紫菜蛋花汤", ("紫菜", "鸡蛋", "水")),
    ("黄瓜蛋花汤", ("黄瓜", "鸡蛋", "水")), ("丝瓜蛋汤", ("丝瓜", "鸡蛋", "水")),
    ("冬瓜虾仁汤", ("冬瓜", "虾", "水")), ("白萝卜鲫鱼汤", ("白萝卜", "鲫鱼", "水")),
    ("番茄豆腐汤", ("番茄", "豆腐", "水")), ("白菜豆腐汤", ("白菜", "豆腐", "水")),
    ("菠菜豆腐汤", ("菠菜", "豆腐", "水")), ("海带豆腐汤", ("海带", "豆腐", "水")),
    ("玉米排骨汤", ("玉米", "猪排骨", "水")), ("莲藕排骨汤", ("莲藕", "猪排骨", "水")),
    ("冬瓜排骨汤", ("冬瓜", "猪排骨", "水")), ("山药排骨汤", ("山药", "猪排骨", "水")),
    ("香菇鸡汤", ("香菇", "整鸡", "水")), ("玉米鸡汤", ("玉米", "整鸡", "水")),
    ("萝卜牛肉汤", ("白萝卜", "牛肉", "水")), ("番茄牛肉汤", ("番茄", "牛肉", "水")),
    ("蛤蜊豆腐汤", ("蛤蜊", "豆腐", "水")), ("银耳红枣汤", ("银耳", "红枣", "水")),
)


_CHINESE_STEAM = (
    ("清蒸鳕鱼", ("鳕鱼", "姜", "小葱")), ("清蒸草鱼", ("草鱼", "姜", "小葱")),
    ("豉汁蒸鱼", ("鱼", "豆豉", "姜")), ("蒜蓉蒸虾", ("虾", "大蒜")),
    ("粉丝蒸扇贝", ("扇贝", "粉丝", "大蒜")), ("蒜蓉蒸蛤蜊", ("蛤蜊", "大蒜")),
    ("香菇蒸鸡", ("香菇", "鸡肉", "姜")), ("红枣蒸鸡", ("红枣", "鸡肉", "姜")),
    ("南瓜蒸排骨", ("南瓜", "猪排骨", "豆豉")), ("芋头蒸排骨", ("芋头", "猪排骨", "豆豉")),
    ("豉汁蒸鸡翅", ("鸡翅", "豆豉", "大蒜")), ("清蒸肉饼", ("肉馅", "马蹄", "小葱")),
    ("鸡蛋蒸肉末", ("鸡蛋", "肉馅", "水")), ("虾仁蒸蛋", ("虾", "鸡蛋", "水")),
    ("蛤蜊蒸蛋", ("蛤蜊", "鸡蛋", "水")), ("豆腐蒸肉末", ("豆腐", "肉馅")),
    ("香菇蒸豆腐", ("香菇", "豆腐")), ("蒜蓉蒸茄子", ("大蒜", "茄子")),
    ("蒜蓉蒸丝瓜", ("大蒜", "丝瓜")), ("粉丝蒸白菜", ("粉丝", "白菜", "大蒜")),
)


_CHINESE_STEWS = (
    ("土豆炖牛肉", ("土豆", "牛肉", "水")), ("萝卜炖牛肉", ("白萝卜", "牛肉", "水")),
    ("番茄炖牛肉", ("番茄", "牛肉", "水")), ("香菇炖鸡", ("香菇", "鸡肉", "水")),
    ("土豆炖鸡", ("土豆", "鸡肉", "水")), ("山药炖鸡", ("山药", "鸡肉", "水")),
    ("莲藕炖鸡", ("莲藕", "鸡肉", "水")), ("白萝卜炖鸡", ("白萝卜", "鸡肉", "水")),
    ("海带炖排骨", ("海带", "猪排骨", "水")), ("冬瓜炖排骨", ("冬瓜", "猪排骨", "水")),
    ("豆角炖排骨", ("豆角", "猪排骨", "水")), ("土豆炖排骨", ("土豆", "猪排骨", "水")),
    ("黄豆炖猪蹄", ("黄豆", "猪蹄", "水")), ("花生炖猪蹄", ("花生", "猪蹄", "水")),
    ("白菜炖五花肉", ("白菜", "五花肉", "水")), ("酸菜炖五花肉", ("酸菜", "五花肉", "水")),
    ("芋头炖五花肉", ("芋头", "五花肉", "水")), ("萝卜炖羊肉", ("白萝卜", "羊肉", "水")),
    ("土豆炖羊肉", ("土豆", "羊肉", "水")), ("白菜炖豆皮", ("白菜", "豆皮", "水")),
)


def _chinese_blueprints() -> list[GoldenBlueprint]:
    collection = PrimaryCollection.CHINESE_HOME
    famous = []
    for index, (name, ingredients) in enumerate(_CHINESE_FAMOUS):
        if index < 13:
            style, region = "SICHUAN", Region.SICHUAN
        elif index < 22:
            style, region = "NORTHERN", Region.OTHER_CHINESE
        elif index < 29:
            style, region = "JIANGZHE", Region.OTHER_CHINESE
        elif index < 37:
            style, region = "CANTONESE", Region.CANTONESE
        else:
            style, region = "NATIONWIDE", Region.CHINESE_HOME
        method = CookingMethod.SIMMER
        if any(token in name for token in (
            "炒", "爆", "干煸", "干锅", "回锅", "宫保", "鱼香", "木须",
            "京酱", "孜然", "滑蛋", "蚝油", "地三鲜",
        )):
            method = CookingMethod.STIR_FRY
        elif any(token in name for token in ("白切", "口水鸡", "蒜泥白肉")):
            method = CookingMethod.BOIL
        elif "叉烧" in name:
            method = CookingMethod.ROAST
        elif "蒸" in name:
            method = CookingMethod.STEAM
        elif any(token in name for token in ("锅包", "咕噜", "辣子", "糖醋")):
            method = CookingMethod.PAN_FRY
        category = RecipeCategory.MAIN_DISH
        famous.append(
            GoldenBlueprint(
                name=name,
                collection=collection,
                style=style,
                ingredients=ingredients,
                method=method,
                category=category,
                total_minutes=45 if method == CookingMethod.SIMMER else 30,
            )
        )
    systematic = _rows(
        _CHINESE_STIR_PAIRS,
        method=CookingMethod.STIR_FRY,
        category=RecipeCategory.MAIN_DISH,
        minutes=25,
        collection=collection,
        style="NATIONWIDE",
    )
    eggs = _rows(
        _CHINESE_EGG,
        method=CookingMethod.STIR_FRY,
        category=RecipeCategory.SIDE_DISH,
        minutes=18,
        collection=collection,
        style="NATIONWIDE",
    )
    tofu = _rows(
        _CHINESE_TOFU,
        method=CookingMethod.SIMMER,
        category=RecipeCategory.MAIN_DISH,
        minutes=28,
        collection=collection,
        style="NATIONWIDE",
    )
    soups = _rows(
        _CHINESE_SOUPS,
        method=CookingMethod.BOIL,
        category=RecipeCategory.SOUP,
        minutes=30,
        collection=collection,
        style="NATIONWIDE",
    )
    steamed = _rows(
        _CHINESE_STEAM,
        method=CookingMethod.STEAM,
        category=RecipeCategory.MAIN_DISH,
        minutes=30,
        collection=collection,
        style="CANTONESE",
    )
    stews = _rows(
        _CHINESE_STEWS,
        method=CookingMethod.SIMMER,
        category=RecipeCategory.MAIN_DISH,
        minutes=50,
        collection=collection,
        style="NORTHERN",
    )
    result = [*famous, *systematic, *eggs, *tofu, *soups, *steamed, *stews]
    assert len(result) == 220
    return result


_QUICK_RICE = (
    ("洋葱鸡蛋炒饭", ("洋葱", "鸡蛋", "米饭")), ("胡萝卜鸡蛋炒饭", ("胡萝卜", "鸡蛋", "米饭")),
    ("青椒鸡蛋炒饭", ("青椒", "鸡蛋", "米饭")), ("毛豆鸡蛋炒饭", ("毛豆", "鸡蛋", "米饭")),
    ("豌豆虾仁炒饭", ("豌豆", "虾", "米饭")), ("玉米鸡肉炒饭", ("玉米", "鸡肉", "米饭")),
    ("香菇鸡肉炒饭", ("香菇", "鸡肉", "米饭")), ("番茄鸡蛋盖饭", ("番茄", "鸡蛋", "米饭")),
    ("咖喱鸡肉盖饭", ("咖喱粉", "鸡肉", "米饭")), ("牛肉洋葱盖饭", ("牛肉", "洋葱", "米饭")),
    ("豆腐香菇盖饭", ("豆腐", "香菇", "米饭")), ("茄子肉末盖饭", ("茄子", "肉馅", "米饭")),
    ("青椒肉丝盖饭", ("青椒", "猪肉", "米饭")), ("番茄牛肉盖饭", ("番茄", "牛肉", "米饭")),
    ("虾仁滑蛋盖饭", ("虾", "鸡蛋", "米饭")), ("金枪鱼拌饭", ("金枪鱼", "米饭", "黄瓜")),
    ("紫菜鸡蛋拌饭", ("紫菜", "鸡蛋", "米饭")), ("黄瓜鸡丝拌饭", ("黄瓜", "鸡肉", "米饭")),
    ("豆豉肉末拌饭", ("豆豉", "肉馅", "米饭")), ("酸豆角肉末拌饭", ("酸豆角", "肉馅", "米饭")),
)


_QUICK_NOODLES = (
    ("番茄鸡蛋面", ("番茄", "鸡蛋", "面条", "水")), ("油菜鸡蛋面", ("油菜", "鸡蛋", "面条", "水")),
    ("葱油拌面", ("小葱", "面条", "生抽")), ("麻酱拌面", ("芝麻酱", "黄瓜", "面条")),
    ("肉末拌面", ("肉馅", "面条", "生抽")), ("酸豆角拌面", ("酸豆角", "肉馅", "面条")),
    ("榨菜肉丝面", ("榨菜", "猪肉", "面条", "水")), ("雪菜鸡丝面", ("雪菜", "鸡肉", "面条", "水")),
    ("香菇鸡肉面", ("香菇", "鸡肉", "面条", "水")), ("番茄牛肉面", ("番茄", "牛肉", "面条", "水")),
    ("虾仁青菜面", ("虾", "油菜", "面条", "水")), ("青椒肉丝炒面", ("青椒", "猪肉", "面条")),
    ("鸡肉蔬菜炒面", ("鸡肉", "胡萝卜", "青椒", "面条")), ("牛肉洋葱炒面", ("牛肉", "洋葱", "面条")),
    ("番茄意大利面", ("番茄", "意大利面", "大蒜")), ("金枪鱼意大利面", ("金枪鱼", "意大利面", "番茄")),
    ("蘑菇奶油意大利面", ("平菇", "淡奶油", "意大利面")), ("西兰花虾仁意大利面", ("西兰花", "虾", "意大利面")),
    ("鸡蛋米粉汤", ("鸡蛋", "米粉", "油菜", "水")), ("酸辣粉丝", ("粉丝", "醋", "辣椒", "水")),
)


_QUICK_BREAKFAST = (
    ("燕麦牛奶粥", ("燕麦", "牛奶", "水")), ("小米南瓜粥", ("小米", "南瓜", "水")),
    ("红豆粥", ("红豆", "大米", "水")), ("绿豆粥", ("绿豆", "大米", "水")),
    ("红枣莲子粥", ("红枣", "莲子", "大米", "水")), ("鸡蛋葱花饼", ("鸡蛋", "小葱", "面粉")),
    ("土豆丝饼", ("土豆", "鸡蛋", "面粉")), ("玉米鸡蛋饼", ("玉米", "鸡蛋", "面粉")),
    ("香蕉燕麦饼", ("香蕉", "燕麦", "鸡蛋")), ("红薯燕麦饼", ("红薯", "燕麦", "鸡蛋")),
    ("蔬菜鸡蛋卷", ("鸡蛋", "胡萝卜", "菠菜")), ("番茄鸡蛋三明治", ("番茄", "鸡蛋", "面包")),
    ("金枪鱼三明治", ("金枪鱼", "黄瓜", "面包")), ("牛油果鸡蛋吐司", ("牛油果", "鸡蛋", "面包")),
    ("花生酱香蕉吐司", ("花生酱", "香蕉", "面包")), ("酸奶水果杯", ("酸奶", "苹果", "香蕉")),
    ("燕麦酸奶杯", ("燕麦", "酸奶", "蓝莓")), ("鸡蛋馒头片", ("鸡蛋", "馒头")),
    ("韭菜盒子", ("韭菜", "鸡蛋", "面粉")), ("紫菜饭团", ("紫菜", "米饭", "黄瓜")),
)


_QUICK_MIXED = (
    ("黄瓜木耳凉拌", ("黄瓜", "木耳", "醋")), ("豆皮黄瓜凉拌", ("豆皮", "黄瓜", "醋")),
    ("金枪鱼玉米沙拉", ("金枪鱼", "玉米", "生菜")), ("牛油果番茄沙拉", ("牛油果", "番茄", "生菜")),
    ("鸡肉生菜卷", ("鸡肉", "生菜", "黄瓜")), ("虾仁黄瓜沙拉", ("虾", "黄瓜", "生菜")),
    ("鹰嘴豆番茄沙拉", ("鹰嘴豆", "番茄", "黄瓜")), ("红豆酸奶杯", ("红豆", "酸奶")),
    ("蓝莓酸奶杯", ("蓝莓", "酸奶", "燕麦")), ("草莓香蕉酸奶杯", ("草莓", "香蕉", "酸奶")),
    ("苹果燕麦杯", ("苹果", "燕麦", "酸奶")), ("梨片核桃酸奶", ("梨", "核桃", "酸奶")),
    ("芝麻酱菠菜拌菜", ("芝麻酱", "菠菜")), ("腐竹黄瓜拌菜", ("腐竹", "黄瓜")),
    ("豆腐番茄拌菜", ("豆腐", "番茄", "小葱")), ("玉米豌豆快炒", ("玉米", "豌豆", "胡萝卜")),
    ("蒜香西兰花快炒", ("大蒜", "西兰花")), ("番茄金针菇快煮", ("番茄", "金针菇", "水")),
    ("榨菜鸡蛋快炒", ("榨菜", "鸡蛋")), ("豆芽韭菜快炒", ("豆芽", "韭菜")),
)


def _quick_blueprints() -> list[GoldenBlueprint]:
    collection = PrimaryCollection.QUICK_EVERYDAY
    result = [
        *_rows(_QUICK_RICE[:15], method=CookingMethod.STIR_FRY, category=RecipeCategory.STAPLE, minutes=20, collection=collection, style="QUICK_RICE"),
        *_rows(_QUICK_RICE[15:], method=CookingMethod.MIX, category=RecipeCategory.STAPLE, minutes=15, collection=collection, style="QUICK_RICE"),
        *_rows(_QUICK_NOODLES[:11], method=CookingMethod.BOIL, category=RecipeCategory.STAPLE, minutes=22, collection=collection, style="QUICK_NOODLE"),
        *_rows(_QUICK_NOODLES[11:14], method=CookingMethod.STIR_FRY, category=RecipeCategory.STAPLE, minutes=22, collection=collection, style="QUICK_NOODLE"),
        *_rows(_QUICK_NOODLES[14:], method=CookingMethod.BOIL, category=RecipeCategory.STAPLE, minutes=22, collection=collection, style="QUICK_NOODLE"),
        *_rows(_QUICK_BREAKFAST[:5], method=CookingMethod.BOIL, category=RecipeCategory.BREAKFAST, minutes=25, collection=collection, style="QUICK_BREAKFAST"),
        *_rows(_QUICK_BREAKFAST[5:15], method=CookingMethod.PAN_FRY, category=RecipeCategory.BREAKFAST, minutes=20, collection=collection, style="QUICK_BREAKFAST"),
        *_rows(_QUICK_BREAKFAST[15:17], method=CookingMethod.MIX, category=RecipeCategory.BREAKFAST, minutes=10, collection=collection, style="QUICK_BREAKFAST"),
        *_rows(_QUICK_BREAKFAST[17:19], method=CookingMethod.PAN_FRY, category=RecipeCategory.BREAKFAST, minutes=25, collection=collection, style="QUICK_BREAKFAST"),
        *_rows(_QUICK_BREAKFAST[19:], method=CookingMethod.MIX, category=RecipeCategory.BREAKFAST, minutes=15, collection=collection, style="QUICK_BREAKFAST"),
        *_rows(_QUICK_MIXED[:15], method=CookingMethod.MIX, category=RecipeCategory.SIDE_DISH, minutes=15, collection=collection, style="QUICK_MIXED"),
        *_rows(_QUICK_MIXED[15:17], method=CookingMethod.STIR_FRY, category=RecipeCategory.SIDE_DISH, minutes=15, collection=collection, style="QUICK_MIXED"),
        *_rows(_QUICK_MIXED[17:18], method=CookingMethod.BOIL, category=RecipeCategory.SIDE_DISH, minutes=15, collection=collection, style="QUICK_MIXED"),
        *_rows(_QUICK_MIXED[18:], method=CookingMethod.STIR_FRY, category=RecipeCategory.SIDE_DISH, minutes=15, collection=collection, style="QUICK_MIXED"),
    ]
    assert len(result) == 80
    return result


_BEGINNER_STIR = (
    ("蒜蓉油菜", ("大蒜", "油菜")), ("蒜蓉空心菜", ("大蒜", "空心菜")),
    ("清炒荷兰豆", ("荷兰豆", "大蒜")), ("蒜蓉生菜", ("大蒜", "生菜")),
    ("清炒西葫芦", ("西葫芦", "大蒜")), ("清炒芦笋", ("芦笋", "大蒜")),
    ("清炒秋葵", ("秋葵", "大蒜")), ("清炒莴笋", ("莴笋", "大蒜")),
    ("蒜蓉菠菜", ("大蒜", "菠菜")), ("清炒豆芽", ("豆芽", "小葱")),
    ("清炒菜花", ("菜花", "大蒜")), ("蒜蓉芥蓝", ("大蒜", "芥蓝")),
    ("清炒茭白", ("茭白", "青椒")), ("清炒丝瓜", ("丝瓜", "大蒜")),
    ("蒜香杏鲍菇", ("大蒜", "杏鲍菇")),
)


_BEGINNER_SOUP = (
    ("玉米蛋花汤", ("玉米", "鸡蛋", "水")), ("油菜鸡蛋汤", ("油菜", "鸡蛋", "水")),
    ("金针菇鸡蛋汤", ("金针菇", "鸡蛋", "水")), ("西葫芦鸡蛋汤", ("西葫芦", "鸡蛋", "水")),
    ("萝卜豆腐汤", ("白萝卜", "豆腐", "水")), ("丝瓜豆腐汤", ("丝瓜", "豆腐", "水")),
    ("香菇油菜汤", ("香菇", "油菜", "水")), ("冬瓜海带汤", ("冬瓜", "海带", "水")),
    ("紫菜豆腐汤", ("紫菜", "豆腐", "水")), ("番茄金针菇汤", ("番茄", "金针菇", "水")),
    ("白菜粉丝汤", ("白菜", "粉丝", "水")), ("菠菜鸡蛋粉丝汤", ("菠菜", "鸡蛋", "粉丝", "水")),
    ("蘑菇蔬菜汤", ("平菇", "胡萝卜", "油菜", "水")), ("南瓜小米汤", ("南瓜", "小米", "水")),
    ("山药玉米汤", ("山药", "玉米", "水")),
)


_BEGINNER_PAN = (
    ("香煎豆腐", ("豆腐", "小葱")), ("香煎土豆片", ("土豆", "黑胡椒")),
    ("香煎南瓜片", ("南瓜", "黑胡椒")), ("香煎鸡肉片", ("鸡肉", "黑胡椒")),
    ("胡萝卜鸡蛋饼", ("胡萝卜", "鸡蛋", "面粉")), ("西葫芦鸡蛋饼", ("西葫芦", "鸡蛋", "面粉")),
    ("菠菜鸡蛋饼", ("菠菜", "鸡蛋", "面粉")), ("土豆洋葱饼", ("土豆", "洋葱", "面粉")),
    ("南瓜燕麦饼", ("南瓜", "燕麦", "鸡蛋")), ("苹果燕麦饼", ("苹果", "燕麦", "鸡蛋")),
    ("豆腐鸡蛋饼", ("豆腐", "鸡蛋", "面粉")), ("玉米蔬菜饼", ("玉米", "胡萝卜", "面粉")),
    ("香煎鳕鱼", ("鳕鱼", "黑胡椒", "柠檬汁")), ("香煎虾饼", ("虾", "鸡蛋", "淀粉")),
    ("馒头鸡蛋煎片", ("馒头", "鸡蛋")),
)


_BEGINNER_STEAM = (
    ("清蒸南瓜", ("南瓜", "水")), ("清蒸红薯", ("红薯", "水")),
    ("清蒸玉米", ("玉米", "水")), ("清蒸山药", ("山药", "水")),
    ("清蒸芋头", ("芋头", "水")), ("红枣蒸南瓜", ("红枣", "南瓜", "水")),
    ("百合蒸南瓜", ("百合", "南瓜", "水")), ("香菇蒸鸡蛋", ("香菇", "鸡蛋", "水")),
    ("菠菜蒸蛋", ("菠菜", "鸡蛋", "水")), ("玉米蒸蛋", ("玉米", "鸡蛋", "水")),
)


def _beginner_blueprints() -> list[GoldenBlueprint]:
    collection = PrimaryCollection.BEGINNER_FRIENDLY
    result = [
        *_rows(_BEGINNER_STIR, method=CookingMethod.STIR_FRY, category=RecipeCategory.SIDE_DISH, minutes=15, collection=collection, style="BEGINNER_STIR"),
        *_rows(_BEGINNER_SOUP, method=CookingMethod.BOIL, category=RecipeCategory.SOUP, minutes=22, collection=collection, style="BEGINNER_SOUP"),
        *_rows(_BEGINNER_PAN[:4], method=CookingMethod.PAN_FRY, category=RecipeCategory.MAIN_DISH, minutes=20, collection=collection, style="BEGINNER_PAN"),
        *_rows(_BEGINNER_PAN[4:], method=CookingMethod.PAN_FRY, category=RecipeCategory.BREAKFAST, minutes=20, collection=collection, style="BEGINNER_PAN"),
        *_rows(_BEGINNER_STEAM, method=CookingMethod.STEAM, category=RecipeCategory.SIDE_DISH, minutes=20, collection=collection, style="BEGINNER_STEAM"),
    ]
    assert len(result) == 55
    return result


_FAMILY_STEWS = (
    ("番茄土豆炖牛肉", ("番茄", "土豆", "牛肉", "水")), ("胡萝卜土豆炖牛肉", ("胡萝卜", "土豆", "牛肉", "水")),
    ("白萝卜香菇炖牛肉", ("白萝卜", "香菇", "牛肉", "水")), ("南瓜炖牛肉", ("南瓜", "牛肉", "水")),
    ("玉米土豆炖鸡", ("玉米", "土豆", "鸡肉", "水")), ("山药香菇炖鸡", ("山药", "香菇", "鸡肉", "水")),
    ("莲藕香菇炖鸡", ("莲藕", "香菇", "鸡肉", "水")), ("南瓜红枣炖鸡", ("南瓜", "鸡肉", "红枣", "水")),
    ("白菜粉丝炖排骨", ("白菜", "粉丝", "猪排骨", "水")), ("玉米山药炖排骨", ("玉米", "山药", "猪排骨", "水")),
    ("莲藕花生炖排骨", ("莲藕", "花生", "猪排骨", "水")), ("冬瓜海带炖排骨", ("冬瓜", "海带", "猪排骨", "水")),
    ("酸菜粉丝炖五花肉", ("酸菜", "粉丝", "五花肉", "水")), ("白菜豆腐炖五花肉", ("白菜", "豆腐", "五花肉", "水")),
    ("土豆胡萝卜炖羊肉", ("土豆", "胡萝卜", "羊肉", "水")), ("萝卜山药炖羊肉", ("白萝卜", "山药", "羊肉", "水")),
    ("番茄豆腐炖鱼", ("番茄", "豆腐", "鱼", "水")), ("酸菜豆腐炖鱼", ("酸菜", "豆腐", "鱼", "水")),
    ("白菜豆腐炖粉条", ("白菜", "豆腐", "粉丝", "水")), ("菌菇豆腐一锅炖", ("香菇", "金针菇", "豆腐", "水")),
    ("番茄鸡蛋豆腐煲", ("番茄", "鸡蛋", "豆腐", "水")), ("茄子土豆豆角煲", ("茄子", "土豆", "豆角", "水")),
    ("海带黄豆炖猪蹄", ("海带", "黄豆", "猪蹄", "水")), ("花生红枣炖猪蹄", ("花生", "红枣", "猪蹄", "水")),
    ("冬瓜蛤蜊豆腐煲", ("冬瓜", "蛤蜊", "豆腐", "水")),
)


_FAMILY_RICE = (
    ("香菇鸡肉焖饭", ("香菇", "鸡肉", "大米", "水")), ("土豆鸡肉焖饭", ("土豆", "鸡肉", "大米", "水")),
    ("南瓜排骨焖饭", ("南瓜", "猪排骨", "大米", "水")), ("胡萝卜牛肉焖饭", ("胡萝卜", "牛肉", "大米", "水")),
    ("豆豉肉末焖饭", ("豆豉", "肉馅", "大米", "水")), ("玉米豌豆焖饭", ("玉米", "豌豆", "大米", "水")),
    ("香菇豆腐焖饭", ("香菇", "豆腐", "大米", "水")), ("番茄牛肉焖饭", ("番茄", "牛肉", "大米", "水")),
    ("芋头排骨焖饭", ("芋头", "猪排骨", "大米", "水")), ("莲藕鸡肉焖饭", ("莲藕", "鸡肉", "大米", "水")),
    ("红薯杂粮焖饭", ("红薯", "小米", "大米", "水")), ("南瓜小米焖饭", ("南瓜", "小米", "大米", "水")),
    ("豆角肉末焖饭", ("豆角", "肉馅", "大米", "水")), ("酸菜五花肉焖饭", ("酸菜", "五花肉", "大米", "水")),
    ("海带排骨焖饭", ("海带", "猪排骨", "大米", "水")),
)


_FAMILY_SOUPS = (
    ("山药莲子鸡汤", ("山药", "莲子", "整鸡", "水")), ("红枣枸杞鸡汤", ("红枣", "枸杞", "整鸡", "水")),
    ("玉米莲藕排骨汤", ("玉米", "莲藕", "猪排骨", "水")), ("山药胡萝卜排骨汤", ("山药", "胡萝卜", "猪排骨", "水")),
    ("番茄玉米牛肉汤", ("番茄", "玉米", "牛肉", "水")), ("萝卜海带牛肉汤", ("白萝卜", "海带", "牛肉", "水")),
    ("冬瓜蛤蜊汤", ("冬瓜", "蛤蜊", "水")), ("丝瓜虾仁豆腐汤", ("丝瓜", "虾", "豆腐", "水")),
    ("菌菇鸡肉汤", ("香菇", "平菇", "鸡肉", "水")), ("白菜肉丸粉丝汤", ("白菜", "肉馅", "粉丝", "水")),
)


def _family_blueprints() -> list[GoldenBlueprint]:
    collection = PrimaryCollection.FAMILY_ONE_POT
    result = [
        *_rows(_FAMILY_STEWS, method=CookingMethod.SIMMER, category=RecipeCategory.MAIN_DISH, minutes=55, collection=collection, style="FAMILY_STEW"),
        *_rows(_FAMILY_RICE, method=CookingMethod.SIMMER, category=RecipeCategory.STAPLE, minutes=45, collection=collection, style="ONE_POT_RICE"),
        *_rows(_FAMILY_SOUPS, method=CookingMethod.SIMMER, category=RecipeCategory.SOUP, minutes=60, collection=collection, style="FAMILY_SOUP"),
    ]
    assert len(result) == 50
    return result


_HEALTHY_STEAM = (
    ("柠檬蒸鳕鱼", ("鳕鱼", "柠檬", "姜")), ("香菇蒸鳕鱼", ("香菇", "鳕鱼", "姜")),
    ("番茄蒸鲈鱼", ("番茄", "鲈鱼", "姜")), ("芦笋蒸虾仁", ("芦笋", "虾")),
    ("冬瓜蒸鸡肉", ("冬瓜", "鸡肉", "姜")), ("南瓜蒸鸡肉", ("南瓜", "鸡肉", "姜")),
    ("香菇蒸鸡胸", ("香菇", "鸡肉", "姜")), ("山药蒸肉饼", ("山药", "肉馅")),
    ("莲藕蒸肉饼", ("莲藕", "肉馅")), ("秋葵蒸蛋", ("秋葵", "鸡蛋", "水")),
    ("西兰花蒸蛋", ("西兰花", "鸡蛋", "水")), ("豆腐蒸虾仁", ("豆腐", "虾")),
    ("冬瓜蒸虾仁", ("冬瓜", "虾")), ("芋头蒸鸡肉", ("芋头", "鸡肉")),
    ("金针菇蒸鸡肉", ("金针菇", "鸡肉")),
)


_HEALTHY_MIX = (
    ("西兰花鸡肉沙拉", ("西兰花", "鸡肉", "生菜")), ("芦笋虾仁沙拉", ("芦笋", "虾", "生菜")),
    ("牛油果鸡蛋沙拉", ("牛油果", "鸡蛋", "生菜")), ("金枪鱼鹰嘴豆沙拉", ("金枪鱼", "鹰嘴豆", "生菜")),
    ("豆腐海带沙拉", ("豆腐", "海带", "黄瓜")), ("鸡丝木耳拌菜", ("鸡肉", "木耳", "黄瓜")),
    ("虾仁豆腐拌菜", ("虾", "豆腐", "黄瓜")), ("毛豆玉米拌菜", ("毛豆", "玉米", "胡萝卜")),
    ("莲藕木耳拌菜", ("莲藕", "木耳", "醋")), ("莴笋胡萝卜拌菜", ("莴笋", "胡萝卜", "醋")),
    ("秋葵豆腐拌菜", ("秋葵", "豆腐", "生抽")), ("菠菜花生拌菜", ("菠菜", "花生", "醋")),
    ("芹菜腐竹拌菜", ("芹菜", "腐竹", "醋")), ("黄瓜金针菇拌菜", ("黄瓜", "金针菇", "醋")),
    ("番茄鹰嘴豆拌菜", ("番茄", "鹰嘴豆", "黄瓜")),
)


_HEALTHY_LIGHT = (
    ("冬瓜鸡肉清汤", ("冬瓜", "鸡肉", "水")), ("丝瓜虾仁清汤", ("丝瓜", "虾", "水")),
    ("芦笋鸡肉清炒", ("芦笋", "鸡肉")), ("西兰花鸡肉清炒", ("西兰花", "鸡肉")),
    ("荷兰豆虾仁清炒", ("荷兰豆", "虾")), ("秋葵虾仁清炒", ("秋葵", "虾")),
    ("山药木耳清炒", ("山药", "木耳")), ("芦笋木耳清炒", ("芦笋", "木耳")),
    ("菌菇豆腐清汤", ("平菇", "香菇", "豆腐", "水")), ("番茄鹰嘴豆汤", ("番茄", "鹰嘴豆", "水")),
    ("南瓜小米粥", ("南瓜", "小米", "水")), ("山药小米粥", ("山药", "小米", "水")),
    ("红豆燕麦粥", ("红豆", "燕麦", "水")), ("绿豆小米粥", ("绿豆", "小米", "水")),
    ("银耳莲子羹", ("银耳", "莲子", "水")),
)


def _healthy_blueprints() -> list[GoldenBlueprint]:
    collection = PrimaryCollection.HEALTHY_LIGHT
    result = [
        *_rows(_HEALTHY_STEAM, method=CookingMethod.STEAM, category=RecipeCategory.MAIN_DISH, minutes=30, collection=collection, style="LIGHT_STEAM"),
        *_rows(_HEALTHY_MIX, method=CookingMethod.MIX, category=RecipeCategory.SIDE_DISH, minutes=20, collection=collection, style="BALANCED_MIX"),
        *_rows(_HEALTHY_LIGHT[:2], method=CookingMethod.BOIL, category=RecipeCategory.SOUP, minutes=30, collection=collection, style="LIGHT_COOKING"),
        *_rows(_HEALTHY_LIGHT[2:8], method=CookingMethod.STIR_FRY, category=RecipeCategory.MAIN_DISH, minutes=25, collection=collection, style="LIGHT_COOKING"),
        *_rows(_HEALTHY_LIGHT[8:], method=CookingMethod.BOIL, category=RecipeCategory.SOUP, minutes=30, collection=collection, style="LIGHT_COOKING"),
    ]
    assert len(result) == 45
    return result


_AIR_FRYER = (
    ("空气炸锅蜜汁鸡翅", ("鸡翅", "蜂蜜", "生抽")), ("空气炸锅蒜香鸡腿", ("鸡腿", "大蒜", "黑胡椒")),
    ("空气炸锅孜然鸡肉", ("鸡肉", "孜然", "洋葱")), ("空气炸锅椒盐排骨", ("猪排骨", "白胡椒", "五香粉")),
    ("空气炸锅黑椒牛肉串", ("牛肉", "洋葱", "黑胡椒")), ("空气炸锅孜然羊排", ("羊排", "孜然")),
    ("空气炸锅柠檬鳕鱼", ("鳕鱼", "柠檬", "黑胡椒")), ("空气炸锅香草鲈鱼", ("鲈鱼", "香叶", "黑胡椒")),
    ("空气炸锅蒜香虾仁", ("虾", "大蒜", "柠檬汁")), ("空气炸锅椒盐鱿鱼", ("鱿鱼", "白胡椒", "淀粉")),
    ("空气炸锅黑椒土豆角", ("土豆", "黑胡椒")), ("空气炸锅孜然红薯条", ("红薯", "孜然")),
    ("空气炸锅蜂蜜南瓜", ("南瓜", "蜂蜜")), ("空气炸锅椒盐芋头", ("芋头", "白胡椒")),
    ("空气炸锅蒜香西兰花", ("西兰花", "大蒜")), ("空气炸锅孜然菜花", ("菜花", "孜然")),
    ("空气炸锅黑椒杏鲍菇", ("杏鲍菇", "黑胡椒")), ("空气炸锅椒盐豆腐", ("豆腐", "淀粉", "白胡椒")),
    ("空气炸锅脆皮腐竹", ("腐竹", "孜然")), ("空气炸锅烤玉米", ("玉米", "黑胡椒")),
    ("空气炸锅烤茄子", ("茄子", "大蒜", "生抽")), ("空气炸锅烤青椒", ("青椒", "大蒜")),
    ("空气炸锅烤秋葵", ("秋葵", "黑胡椒")), ("空气炸锅烤芦笋", ("芦笋", "黑胡椒")),
    ("空气炸锅苹果燕麦酥", ("苹果", "燕麦", "蜂蜜")), ("空气炸锅香蕉燕麦饼", ("香蕉", "燕麦", "鸡蛋")),
    ("空气炸锅红薯燕麦球", ("红薯", "燕麦")), ("空气炸锅面包布丁", ("面包", "鸡蛋", "牛奶")),
    ("空气炸锅芝麻馒头片", ("馒头", "芝麻")), ("空气炸锅花生豆腐丸", ("花生", "豆腐", "淀粉")),
)


def _air_blueprints() -> list[GoldenBlueprint]:
    savory = _rows(
        _AIR_FRYER[:24],
        method=CookingMethod.AIR_FRY,
        category=RecipeCategory.MAIN_DISH,
        minutes=30,
        collection=PrimaryCollection.AIR_FRYER_APPLIANCE,
        style="AIR_FRYER",
    )
    snacks = _rows(
        _AIR_FRYER[24:],
        method=CookingMethod.AIR_FRY,
        category=RecipeCategory.SNACK,
        minutes=30,
        collection=PrimaryCollection.AIR_FRYER_APPLIANCE,
        style="AIR_FRYER",
    )
    result = [*savory, *snacks]
    assert len(result) == 30
    return result


_OTHER_HOUSEHOLD = (
    ("苹果银耳羹", ("苹果", "银耳", "水")), ("梨枣银耳羹", ("梨", "红枣", "银耳", "水")),
    ("红豆莲子甜汤", ("红豆", "莲子", "水")), ("绿豆百合汤", ("绿豆", "百合", "水")),
    ("南瓜红枣甜汤", ("南瓜", "红枣", "水")), ("花生核桃燕麦粥", ("花生", "核桃", "燕麦", "水")),
    ("香蕉牛奶燕麦杯", ("香蕉", "牛奶", "燕麦")), ("草莓蓝莓酸奶杯", ("草莓", "蓝莓", "酸奶")),
    ("苹果核桃酸奶杯", ("苹果", "核桃", "酸奶")), ("菠萝香蕉酸奶杯", ("菠萝", "香蕉", "酸奶")),
    ("芝麻花生糯米团", ("芝麻", "花生", "糯米")), ("红豆糯米团", ("红豆", "糯米")),
    ("南瓜糯米饼", ("南瓜", "糯米")), ("红薯糯米饼", ("红薯", "糯米")),
    ("苹果肉桂烤燕麦", ("苹果", "燕麦", "桂皮")), ("蓝莓香蕉烤燕麦", ("蓝莓", "香蕉", "燕麦")),
    ("花生酱燕麦能量球", ("花生酱", "燕麦", "蜂蜜")), ("芝麻核桃能量球", ("芝麻", "核桃", "蜂蜜")),
    ("玉米面发糕", ("玉米", "面粉", "泡打粉")), ("红枣燕麦发糕", ("红枣", "燕麦", "面粉", "泡打粉")),
)


def _other_blueprints() -> list[GoldenBlueprint]:
    cooked_desserts = _rows(
        _OTHER_HOUSEHOLD[:6], method=CookingMethod.BOIL,
        category=RecipeCategory.DESSERT, minutes=30,
        collection=PrimaryCollection.OTHER_HOUSEHOLD, style="HOUSEHOLD_DESSERT",
    )
    cold_desserts = _rows(
        _OTHER_HOUSEHOLD[6:10], method=CookingMethod.MIX,
        category=RecipeCategory.DESSERT, minutes=10,
        collection=PrimaryCollection.OTHER_HOUSEHOLD, style="HOUSEHOLD_DESSERT",
    )
    cold_shaped_snacks = _rows(
        _OTHER_HOUSEHOLD[10:12], method=CookingMethod.MIX,
        category=RecipeCategory.SNACK, minutes=25,
        collection=PrimaryCollection.OTHER_HOUSEHOLD, style="HOUSEHOLD_SNACK",
    )
    pan_snacks = _rows(
        _OTHER_HOUSEHOLD[12:14], method=CookingMethod.PAN_FRY,
        category=RecipeCategory.SNACK, minutes=35,
        collection=PrimaryCollection.OTHER_HOUSEHOLD, style="HOUSEHOLD_SNACK",
    )
    baked_snacks = _rows(
        _OTHER_HOUSEHOLD[14:], method=CookingMethod.BAKE,
        category=RecipeCategory.SNACK, minutes=35,
        collection=PrimaryCollection.OTHER_HOUSEHOLD, style="HOUSEHOLD_SNACK",
    )
    result = [*cooked_desserts, *cold_desserts, *cold_shaped_snacks, *pan_snacks, *baked_snacks]
    assert len(result) == 20
    return result


def get_golden_blueprints() -> list[GoldenBlueprint]:
    blueprints = [
        *_chinese_blueprints(),
        *_quick_blueprints(),
        *_beginner_blueprints(),
        *_family_blueprints(),
        *_healthy_blueprints(),
        *_air_blueprints(),
        *_other_blueprints(),
    ]
    assert len(blueprints) == 500
    names = [blueprint.name.casefold() for blueprint in blueprints]
    if len(names) != len(set(names)):
        duplicates = sorted({name for name in names if names.count(name) > 1})
        raise ValueError(f"golden blueprint names must be unique: {duplicates}")
    return blueprints


def region_for_style(style: str) -> Region:
    if style == "SICHUAN":
        return Region.SICHUAN
    if style == "CANTONESE":
        return Region.CANTONESE
    if style in {"JIANGZHE", "NORTHERN"}:
        return Region.OTHER_CHINESE
    if style.startswith("AIR_") or style in {
        "QUICK_MIXED", "HOUSEHOLD_DESSERT", "HOUSEHOLD_SNACK"
    }:
        return Region.GLOBAL_HOME
    return Region.CHINESE_HOME


def cuisine_for_style(style: str) -> Cuisine:
    if style.startswith("AIR_") or style in {
        "QUICK_MIXED", "HOUSEHOLD_DESSERT", "HOUSEHOLD_SNACK"
    }:
        return Cuisine.FUSION
    return Cuisine.CHINESE
