"""Deterministic ingredient identity based on a controlled alias dictionary."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid5


class UnknownIngredientError(ValueError):
    """Raised when a raw ingredient is absent from the controlled catalog."""


def normalize_lookup_key(value: str) -> str:
    return re.sub(r"[\s_\-]+", "", value.strip().casefold())


@dataclass(frozen=True, slots=True)
class IngredientEntry:
    ingredient_id: UUID
    normalized_name: str
    aliases: tuple[str, ...]


def _entry(name: str, *aliases: str) -> IngredientEntry:
    return IngredientEntry(
        ingredient_id=uuid5(NAMESPACE_URL, f"ai-cooker:ingredient:{name}"),
        normalized_name=name,
        aliases=(name, *aliases),
    )


DEFAULT_INGREDIENTS = (
    _entry("番茄", "西红柿", "tomato", "tomatoes"),
    _entry("鸡蛋", "蛋", "egg", "eggs"),
    _entry("鸡肉", "鸡胸肉", "chicken", "chicken breast"),
    _entry("土豆", "马铃薯", "potato", "potatoes"),
    _entry("米饭", "熟米饭", "rice", "cooked rice"),
    _entry("豆腐", "tofu"),
    _entry("菠菜", "spinach"),
    _entry("食用油", "油", "cooking oil", "oil"),
    _entry("盐", "食盐", "salt"),
    _entry("水", "清水", "water"),
    _entry("洋葱", "onion"),
    _entry("大蒜", "蒜", "蒜瓣", "garlic"),
    _entry("胡萝卜", "carrot", "carrots"),
    _entry("西兰花", "花椰菜", "broccoli"),
    _entry("猪肉", "猪里脊", "猪肉末", "肉末", "pork", "ground pork"),
    _entry("牛肉", "牛里脊", "beef"),
    _entry("鸡腿", "鸡腿肉", "chicken thigh"),
    _entry("鸡翅", "chicken wing", "chicken wings"),
    _entry("虾", "虾仁", "shrimp", "prawn"),
    _entry("鱼", "鱼肉", "白身鱼", "fish", "white fish"),
    _entry("三文鱼", "鲑鱼", "salmon"),
    _entry("牛奶", "milk"),
    _entry("酸奶", "yogurt", "yoghurt"),
    _entry("奶酪", "芝士", "cheese"),
    _entry("面条", "挂面", "noodle", "noodles"),
    _entry("面粉", "小麦粉", "flour", "wheat flour"),
    _entry("燕麦", "燕麦片", "oat", "oats"),
    _entry("玉米", "玉米粒", "corn"),
    _entry("红薯", "地瓜", "sweet potato"),
    _entry("青椒", "green pepper", "green bell pepper"),
    _entry("彩椒", "甜椒", "bell pepper"),
    _entry("黄瓜", "cucumber"),
    _entry("茄子", "eggplant", "aubergine"),
    _entry("白菜", "大白菜", "Chinese cabbage", "napa cabbage"),
    _entry("生菜", "lettuce"),
    _entry("芹菜", "celery"),
    _entry("豆角", "四季豆", "green bean", "green beans"),
    _entry("蘑菇", "口蘑", "mushroom", "mushrooms"),
    _entry("香菇", "shiitake", "shiitake mushroom"),
    _entry("南瓜", "pumpkin"),
    _entry("冬瓜", "wax gourd", "winter melon"),
    _entry("莲藕", "藕", "lotus root"),
    _entry("山药", "Chinese yam"),
    _entry("西葫芦", "zucchini", "courgette"),
    _entry("菜花", "白花椰菜", "cauliflower"),
    _entry("豌豆", "青豆", "pea", "peas"),
    _entry("韭菜", "Chinese chives", "garlic chives"),
    _entry("小葱", "葱", "葱花", "scallion", "spring onion"),
    _entry("姜", "生姜", "ginger"),
    _entry("香菜", "芫荽", "cilantro", "coriander"),
    _entry("白萝卜", "萝卜", "daikon", "white radish"),
    _entry("豆芽", "绿豆芽", "bean sprouts"),
    _entry("毛豆", "edamame"),
    _entry("鹰嘴豆", "chickpea", "chickpeas"),
    _entry("海带", "kelp"),
    _entry("紫菜", "seaweed", "nori"),
    _entry("苹果", "apple", "apples"),
    _entry("香蕉", "banana", "bananas"),
    _entry("柠檬", "lemon"),
    _entry("生抽", "酱油", "light soy sauce", "soy sauce"),
    _entry("老抽", "dark soy sauce"),
    _entry("醋", "米醋", "陈醋", "vinegar", "rice vinegar"),
    _entry("白糖", "糖", "sugar"),
    _entry("黑胡椒", "黑胡椒粉", "black pepper"),
    _entry("淀粉", "玉米淀粉", "cornstarch", "starch"),
    _entry("料酒", "cooking wine", "Shaoxing wine"),
    _entry("芝麻油", "香油", "sesame oil"),
    _entry("蚝油", "oyster sauce"),
    _entry("豆瓣酱", "chili bean paste", "doubanjiang"),
    _entry("辣椒", "红辣椒", "chili", "chilli"),
    _entry("花椒", "Sichuan pepper", "Sichuan peppercorn"),
    _entry("咖喱粉", "curry powder"),
    _entry("番茄酱", "ketchup", "tomato paste"),
    _entry("蜂蜜", "honey"),
    _entry("面包糠", "breadcrumbs", "bread crumbs"),
    _entry("芝麻", "sesame", "sesame seeds"),
)


# Step 17G: Codex-curated vocabulary additions. These are reviewed canonical
# concepts, not aliases invented during recipe normalization. IDs remain stable
# because `_entry` derives them from the canonical Chinese name.
GOLDEN_INGREDIENT_ENTRIES = (
    _entry("猪排骨", "排骨", "pork ribs"),
    _entry("五花肉", "pork belly"),
    _entry("猪蹄", "猪脚", "pig trotter"),
    _entry("猪肝", "pork liver"),
    _entry("猪肚", "pork tripe"),
    _entry("肉馅", "肉末馅", "minced meat filling"),
    _entry("鸡胗", "chicken gizzard"),
    _entry("鸡爪", "凤爪", "chicken feet"),
    _entry("整鸡", "whole chicken"),
    _entry("鸭肉", "鸭", "duck"),
    _entry("鸭腿", "duck leg"),
    _entry("羊肉", "lamb", "mutton"),
    _entry("羊排", "lamb ribs", "lamb chops"),
    _entry("鲈鱼", "sea bass"),
    _entry("草鱼", "grass carp"),
    _entry("鲫鱼", "crucian carp"),
    _entry("鳕鱼", "cod"),
    _entry("带鱼", "hairtail"),
    _entry("金枪鱼", "tuna"),
    _entry("鱿鱼", "squid"),
    _entry("蛤蜊", "花蛤", "clam"),
    _entry("扇贝", "scallop"),
    _entry("螃蟹", "蟹", "crab"),
    _entry("木耳", "黑木耳", "wood ear mushroom"),
    _entry("银耳", "white fungus"),
    _entry("杏鲍菇", "king oyster mushroom"),
    _entry("金针菇", "enoki mushroom"),
    _entry("平菇", "oyster mushroom"),
    _entry("竹笋", "笋", "bamboo shoot"),
    _entry("莴笋", "莴苣笋", "celtuce"),
    _entry("油菜", "小油菜", "bok choy"),
    _entry("空心菜", "water spinach"),
    _entry("芥蓝", "Chinese kale"),
    _entry("蒜薹", "蒜苔", "garlic shoots"),
    _entry("荷兰豆", "snow pea"),
    _entry("秋葵", "okra"),
    _entry("苦瓜", "bitter melon"),
    _entry("丝瓜", "loofah"),
    _entry("芦笋", "asparagus"),
    _entry("韭黄", "yellow chives"),
    _entry("雪菜", "雪里蕻", "preserved mustard greens"),
    _entry("酸菜", "pickled mustard greens"),
    _entry("芋头", "taro"),
    _entry("茭白", "water bamboo"),
    _entry("马蹄", "荸荠", "water chestnut"),
    _entry("黄豆", "soybean"),
    _entry("黑豆", "black bean"),
    _entry("红豆", "red bean"),
    _entry("绿豆", "mung bean"),
    _entry("花生", "peanut"),
    _entry("核桃", "walnut"),
    _entry("腰果", "cashew"),
    _entry("小米", "millet"),
    _entry("大米", "生米", "uncooked rice"),
    _entry("糯米", "glutinous rice"),
    _entry("年糕", "rice cake"),
    _entry("米粉", "rice noodles"),
    _entry("粉丝", "vermicelli"),
    _entry("意大利面", "pasta", "spaghetti"),
    _entry("面包", "bread"),
    _entry("馒头", "steamed bun"),
    _entry("饺子皮", "dumpling wrapper"),
    _entry("馄饨皮", "wonton wrapper"),
    _entry("豆皮", "豆腐皮", "tofu skin"),
    _entry("腐竹", "dried tofu stick"),
    _entry("酸豆角", "pickled long bean"),
    _entry("榨菜", "preserved mustard tuber"),
    _entry("百合", "lily bulb"),
    _entry("红枣", "red date", "jujube"),
    _entry("枸杞", "goji berry"),
    _entry("莲子", "lotus seed"),
    _entry("冬笋", "winter bamboo shoot"),
    _entry("春笋", "spring bamboo shoot"),
    _entry("菠萝", "pineapple"),
    _entry("梨", "pear"),
    _entry("橙子", "orange"),
    _entry("草莓", "strawberry"),
    _entry("蓝莓", "blueberry"),
    _entry("牛油果", "鳄梨", "avocado"),
    _entry("椰奶", "coconut milk"),
    _entry("黄油", "butter"),
    _entry("淡奶油", "cream"),
    _entry("豆豉", "fermented black bean"),
    _entry("黄豆酱", "soybean paste"),
    _entry("甜面酱", "sweet bean paste"),
    _entry("芝麻酱", "sesame paste"),
    _entry("花生酱", "peanut butter"),
    _entry("沙茶酱", "satay sauce"),
    _entry("鱼露", "fish sauce"),
    _entry("辣椒酱", "chili sauce"),
    _entry("白胡椒", "white pepper"),
    _entry("五香粉", "five-spice powder"),
    _entry("孜然", "cumin"),
    _entry("八角", "star anise"),
    _entry("桂皮", "cinnamon bark"),
    _entry("香叶", "bay leaf"),
    _entry("米酒", "rice wine"),
    _entry("柠檬汁", "lemon juice"),
    _entry("泡打粉", "baking powder"),
    _entry("冰糖", "rock sugar"),
)

DEFAULT_INGREDIENTS = (*DEFAULT_INGREDIENTS, *GOLDEN_INGREDIENT_ENTRIES)


class IngredientCatalog:
    """Small controlled vocabulary; unknown values are rejected, never guessed."""

    def __init__(self, entries: tuple[IngredientEntry, ...] = DEFAULT_INGREDIENTS):
        self._by_alias: dict[str, IngredientEntry] = {}
        self._by_id: dict[UUID, IngredientEntry] = {}
        for item in entries:
            if item.ingredient_id in self._by_id:
                raise ValueError(f"duplicate ingredient id: {item.ingredient_id}")
            self._by_id[item.ingredient_id] = item
            for alias in item.aliases:
                key = normalize_lookup_key(alias)
                existing = self._by_alias.get(key)
                if existing is not None and existing != item:
                    raise ValueError(f"ambiguous ingredient alias: {alias}")
                self._by_alias[key] = item

    def resolve(self, name: str) -> IngredientEntry:
        item = self._by_alias.get(normalize_lookup_key(name))
        if item is None:
            raise UnknownIngredientError(
                f"ingredient is not in the controlled catalog: {name!r}"
            )
        return item

    def get(self, ingredient_id: UUID) -> IngredientEntry | None:
        return self._by_id.get(ingredient_id)

    @property
    def entries(self) -> tuple[IngredientEntry, ...]:
        return tuple(self._by_id.values())

    @property
    def canonical_names(self) -> tuple[str, ...]:
        return tuple(item.normalized_name for item in self._by_id.values())
