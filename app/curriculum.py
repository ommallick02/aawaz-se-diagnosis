"""Skill graph, misconception catalog and diagnostic question bank.

Each skill lists the misconceptions Sarvam-105B is asked to look for, and each
question is written to make a child *explain* their reasoning out loud so the
misconception surfaces in what they say, not just in the final answer.
"""

LANGUAGES = [
    {"code": "hi-IN", "name": "हिन्दी", "english": "Hindi"},
    {"code": "en-IN", "name": "English", "english": "English"},
    {"code": "bn-IN", "name": "বাংলা", "english": "Bengali"},
    {"code": "mr-IN", "name": "मराठी", "english": "Marathi"},
    {"code": "ta-IN", "name": "தமிழ்", "english": "Tamil"},
    {"code": "te-IN", "name": "తెలుగు", "english": "Telugu"},
    {"code": "kn-IN", "name": "ಕನ್ನಡ", "english": "Kannada"},
    {"code": "ml-IN", "name": "മലയാളം", "english": "Malayalam"},
    {"code": "gu-IN", "name": "ગુજરાતી", "english": "Gujarati"},
    {"code": "pa-IN", "name": "ਪੰਜਾਬੀ", "english": "Punjabi"},
    {"code": "od-IN", "name": "ଓଡ଼ିଆ", "english": "Odia"},
]
LANGUAGE_NAMES = {l["code"]: l["english"] for l in LANGUAGES}
VOICE_GENDER = {"priya": "female", "shubh": "male", "kavya": "female", "rahul": "male"}

VOICES = [
    {"id": "priya", "label": "Priya", "gender": "female"},
    {"id": "shubh", "label": "Shubh", "gender": "male"},
    {"id": "kavya", "label": "Kavya", "gender": "female"},
    {"id": "rahul", "label": "Rahul", "gender": "male"},
]

MODALITIES = {
    "story": {
        "label": "Story",
        "label_hi": "कहानी",
        "brief": "A short, vivid story set in everyday Indian life (a mela, a cricket match, a "
                 "kirana shop, a family meal) in which a character makes the same mistake and "
                 "discovers why it is wrong.",
    },
    "number_line": {
        "label": "Number line",
        "label_hi": "संख्या रेखा",
        "brief": "Walk the child along a number line step by step: where each quantity sits, "
                 "which way is bigger, and how jumps work. You MUST fill number_line with the "
                 "exact marks and jumps the narration refers to.",
    },
    "analogy": {
        "label": "Real-life analogy",
        "label_hi": "रोज़मर्रा का उदाहरण",
        "brief": "Map the concept onto something the child handles daily — rupees and paise, "
                 "sharing rotis or laddoos, cricket scores, temperature, floors of a building.",
    },
    "visual": {
        "label": "Picture model",
        "label_hi": "चित्र मॉडल",
        "brief": "Build a concrete picture model: fraction bars, equal-part strips, groups of "
                 "objects, or place-value blocks. You MUST fill bars with the strips the "
                 "narration describes (each bar = a whole split into equal parts, some shaded).",
    },
}

SKILLS = [
    {
        "id": "place_value",
        "short": "Place value",
        "name": "Place value",
        "name_hi": "स्थानीय मान",
        "prereqs": [],
        "keyterms": ["place value", "ones", "tens", "hundreds", "thousands", "digit",
                     "इकाई", "दहाई", "सैकड़ा", "हज़ार", "स्थानीय मान", "अंक"],
        "misconceptions": [
            {"id": "pv_face_value", "label": "Face value = place value",
             "description": "Treats a digit's value as the digit itself, ignoring its position "
                            "(says the 4 in 3,456 is worth 4)."},
            {"id": "pv_zero_placeholder", "label": "Zero can be dropped",
             "description": "Omits or misplaces zero as a placeholder (writes four hundred five "
                            "as 45 or 4005)."},
            {"id": "pv_big_digits", "label": "Bigger digits mean a bigger number",
             "description": "Compares numbers by how big their digits are instead of how many "
                            "places they have (thinks 899 > 1,002 because 8 and 9 are big)."},
        ],
        "questions": [
            {"id": "pv1", "answer": "1,002",
             "en": "Which number is bigger: 899 or 1,002? Explain how you decided.",
             "hi": "कौन-सी संख्या बड़ी है: 899 या 1,002? बताओ तुमने कैसे तय किया।"},
            {"id": "pv2", "answer": "400 (four hundreds)",
             "en": "In the number 3,456, what is the value of the digit 4? Tell me how you know.",
             "hi": "संख्या 3,456 में अंक 4 का मान क्या है? बताओ तुम्हें कैसे पता।"},
            {"id": "pv3", "answer": "405",
             "en": "Write 'four hundred and five' in digits. What does each digit mean?",
             "hi": "'चार सौ पाँच' को अंकों में लिखो। हर अंक का क्या मतलब है?"},
        ],
    },
    {
        "id": "addition_regrouping",
        "short": "Carrying",
        "name": "Addition with carrying",
        "name_hi": "हासिल वाला जोड़",
        "prereqs": ["place_value"],
        "keyterms": ["carry", "carry over", "ones", "tens", "add", "हासिल", "जोड़", "इकाई", "दहाई"],
        "misconceptions": [
            {"id": "add_no_carry", "label": "Writes the whole column sum",
             "description": "Writes both digits of a column sum into the answer instead of "
                            "carrying (47 + 38 = 715)."},
            {"id": "add_carry_forgotten", "label": "Forgets the carried digit",
             "description": "Notices the carry but never adds it to the next column "
                            "(47 + 38 = 75)."},
            {"id": "add_misalign", "label": "Lines numbers up from the left",
             "description": "Aligns numbers of different lengths by their first digit, mixing "
                            "up places (156 + 27 treated as 156 + 270)."},
        ],
        "questions": [
            {"id": "add1", "answer": "85",
             "en": "What is 47 + 38? Tell me each step you did.",
             "hi": "47 + 38 कितना होता है? हर कदम बताओ जो तुमने किया।"},
            {"id": "add2", "answer": "183",
             "en": "Add 156 and 27. Explain how you lined up the numbers.",
             "hi": "156 और 27 को जोड़ो। बताओ तुमने संख्याओं को एक के नीचे एक कैसे लिखा।"},
        ],
    },
    {
        "id": "subtraction_borrowing",
        "short": "Borrowing",
        "name": "Subtraction with borrowing",
        "name_hi": "उधार वाला घटाव",
        "prereqs": ["place_value"],
        "keyterms": ["borrow", "subtract", "minus", "ones", "tens", "उधार", "घटाना", "इकाई", "दहाई"],
        "misconceptions": [
            {"id": "sub_smaller_from_larger", "label": "Always takes smaller from larger",
             "description": "In each column subtracts the smaller digit from the larger one, "
                            "whichever is on top (52 − 37 = 25)."},
            {"id": "sub_borrow_no_reduce", "label": "Borrows without reducing",
             "description": "Adds ten to the ones but forgets to take one away from the tens "
                            "(52 − 37: 12 − 7 = 5, then 5 − 3 = 2, so 25)."},
            {"id": "sub_zero_borrow", "label": "Stuck borrowing across zero",
             "description": "Cannot borrow from a zero, so skips or mangles that column "
                            "(300 − 128 = 228 or 282)."},
        ],
        "questions": [
            {"id": "sub1", "answer": "15",
             "en": "What is 52 − 37? Explain every step.",
             "hi": "52 − 37 कितना होता है? हर कदम समझाओ।"},
            {"id": "sub2", "answer": "172",
             "en": "What is 300 − 128? Tell me how you borrowed.",
             "hi": "300 − 128 कितना होता है? बताओ तुमने उधार कैसे लिया।"},
        ],
    },
    {
        "id": "negative_numbers",
        "short": "Negatives",
        "name": "Negative numbers",
        "name_hi": "ऋणात्मक संख्याएँ",
        "prereqs": ["subtraction_borrowing"],
        "keyterms": ["minus", "negative", "below zero", "temperature", "degrees",
                     "ऋणात्मक", "माइनस", "शून्य से नीचे", "तापमान", "डिग्री"],
        "misconceptions": [
            {"id": "neg_magnitude", "label": "Bigger digit → bigger negative",
             "description": "Thinks −8 is bigger than −3 because 8 is bigger than 3."},
            {"id": "neg_ignore_sign", "label": "Ignores the minus sign",
             "description": "Drops the negative sign while adding or subtracting "
                            "(−2 + 5 = 7)."},
            {"id": "neg_zero_smallest", "label": "Zero is the smallest number",
             "description": "Believes nothing can be less than zero."},
        ],
        "questions": [
            {"id": "ng1", "answer": "−3",
             "en": "Which is bigger: −8 or −3? Explain.",
             "hi": "कौन बड़ा है: −8 या −3? समझाओ।"},
            {"id": "ng2", "answer": "3°C",
             "en": "It is −2°C in Shimla in the morning. By noon it is 5 degrees warmer. "
                   "What is the temperature at noon? Explain.",
             "hi": "सुबह शिमला में तापमान −2°C है। दोपहर तक 5 डिग्री गर्मी बढ़ जाती है। "
                   "दोपहर में तापमान कितना है? समझाओ।"},
        ],
    },
    {
        "id": "multiplication_meaning",
        "short": "Multiplication",
        "name": "Meaning of multiplication",
        "name_hi": "गुणा का अर्थ",
        "prereqs": ["addition_regrouping"],
        "keyterms": ["times", "groups", "multiply", "repeated addition", "table",
                     "गुणा", "बार", "समूह", "पहाड़ा"],
        "misconceptions": [
            {"id": "mul_as_addition", "label": "Adds instead of multiplying",
             "description": "Treats 'groups of' as adding the two numbers (4 plates of 3 "
                            "laddoos = 7)."},
            {"id": "mul_zero_identity", "label": "× 0 leaves the number unchanged",
             "description": "Believes multiplying by zero gives back the same number "
                            "(7 × 0 = 7)."},
            {"id": "mul_rote_only", "label": "Tables without meaning",
             "description": "Gets the product from a memorised table but cannot explain it "
                            "as equal groups or repeated addition."},
        ],
        "questions": [
            {"id": "mul1", "answer": "12",
             "en": "There are 4 plates with 3 laddoos on each plate. How many laddoos are there "
                   "in all? Explain how you thought.",
             "hi": "4 प्लेटें हैं और हर प्लेट में 3 लड्डू हैं। कुल कितने लड्डू हैं? "
                   "बताओ तुमने कैसे सोचा।"},
            {"id": "mul2", "answer": "0",
             "en": "What is 7 × 0? Why?",
             "hi": "7 × 0 कितना होता है? क्यों?"},
        ],
    },
    {
        "id": "fraction_meaning",
        "short": "Fractions",
        "name": "What a fraction means",
        "name_hi": "भिन्न का अर्थ",
        "prereqs": ["multiplication_meaning"],
        "keyterms": ["fraction", "numerator", "denominator", "equal parts", "half", "quarter",
                     "भिन्न", "अंश", "हर", "बराबर भाग", "आधा", "चौथाई", "तिहाई"],
        "misconceptions": [
            {"id": "frac_unequal_parts", "label": "Parts need not be equal",
             "description": "Calls any piece 'one-third' when there are three pieces, even if "
                            "the pieces are different sizes."},
            {"id": "frac_part_part", "label": "Part-to-part, not part-to-whole",
             "description": "Compares the taken part with the leftover part instead of with "
                            "the whole (ate 3 of 4 pieces → 3/1)."},
            {"id": "frac_two_numbers", "label": "A fraction is two separate numbers",
             "description": "Sees the numerator and denominator as two unrelated whole numbers "
                            "rather than one quantity."},
        ],
        "questions": [
            {"id": "fm1", "answer": "3/4",
             "en": "A roti is cut into 4 equal pieces and you eat 3 pieces. What fraction of "
                   "the roti did you eat? Explain.",
             "hi": "एक रोटी के 4 बराबर टुकड़े किए गए और तुमने 3 टुकड़े खा लिए। तुमने रोटी का "
                   "कितना भाग खाया? समझाओ।"},
            {"id": "fm2", "answer": "No — the three pieces must be equal to be thirds",
             "en": "A cake is cut into 3 pieces of different sizes. Is each piece one-third of "
                   "the cake? Why or why not?",
             "hi": "एक केक को अलग-अलग आकार के 3 टुकड़ों में काटा गया। क्या हर टुकड़ा केक का "
                   "एक-तिहाई है? क्यों या क्यों नहीं?"},
        ],
    },
    {
        "id": "fraction_compare",
        "short": "Compare fractions",
        "name": "Comparing fractions",
        "name_hi": "भिन्नों की तुलना",
        "prereqs": ["fraction_meaning"],
        "keyterms": ["fraction", "bigger", "smaller", "half", "third", "denominator",
                     "numerator", "भिन्न", "बड़ा", "छोटा", "आधा", "तिहाई", "हर", "अंश"],
        "misconceptions": [
            {"id": "frac_bigger_denominator", "label": "Bigger denominator → bigger fraction",
             "description": "Thinks a larger denominator means a larger fraction "
                            "(1/3 > 1/2 because 3 > 2)."},
            {"id": "frac_gap", "label": "Compares by the gap",
             "description": "Judges fractions by the difference between numerator and "
                            "denominator (3/4 = 5/6 because both are 'one short')."},
            {"id": "frac_numerator_only", "label": "Looks only at numerators",
             "description": "Compares numerators while ignoring different denominators "
                            "(2/7 > 1/2 because 2 > 1)."},
        ],
        "questions": [
            {"id": "fc1", "answer": "1/2",
             "en": "Which is bigger, 1/2 or 1/3? Explain your thinking.",
             "hi": "कौन बड़ा है, 1/2 या 1/3? अपनी सोच समझाओ।"},
            {"id": "fc2", "answer": "5/6",
             "en": "Which is bigger, 3/4 or 5/6? How do you know?",
             "hi": "कौन बड़ा है, 3/4 या 5/6? तुम्हें कैसे पता?"},
            {"id": "fc3", "answer": "smaller",
             "en": "Is 2/7 bigger or smaller than 1/2? Explain.",
             "hi": "2/7, 1/2 से बड़ा है या छोटा? समझाओ।"},
        ],
    },
    {
        "id": "decimal_compare",
        "short": "Decimals",
        "name": "Comparing decimals",
        "name_hi": "दशमलव की तुलना",
        "prereqs": ["place_value", "fraction_meaning"],
        "keyterms": ["decimal", "point", "tenths", "hundredths", "दशमलव", "दशांश", "शतांश",
                     "पॉइंट"],
        "misconceptions": [
            {"id": "dec_longer_bigger", "label": "Longer decimal is bigger",
             "description": "Thinks more digits after the point makes a number bigger "
                            "(0.125 > 0.5)."},
            {"id": "dec_shorter_bigger", "label": "Shorter decimal is bigger",
             "description": "Thinks fewer digits after the point makes a number bigger, "
                            "because 'tenths are bigger than hundredths' (0.4 > 0.45)."},
            {"id": "dec_whole_after_point", "label": "Reads after-point digits as a whole number",
             "description": "Treats the digits after the point as a whole number "
                            "(0.12 > 0.9 because 12 > 9)."},
        ],
        "questions": [
            {"id": "dc1", "answer": "0.5",
             "en": "Which is bigger: 0.5 or 0.125? Explain.",
             "hi": "कौन बड़ा है: 0.5 या 0.125? समझाओ।"},
            {"id": "dc2", "answer": "0.12, 0.45, 0.9",
             "en": "Put 0.9, 0.12 and 0.45 in order from smallest to biggest. Explain how.",
             "hi": "0.9, 0.12 और 0.45 को सबसे छोटे से सबसे बड़े के क्रम में लगाओ। बताओ कैसे।"},
        ],
    },
    {
        "id": "fraction_addition",
        "short": "Add fractions",
        "name": "Adding fractions",
        "name_hi": "भिन्नों का जोड़",
        "prereqs": ["fraction_compare"],
        "keyterms": ["fraction", "add", "common denominator", "LCM", "numerator", "denominator",
                     "भिन्न", "जोड़", "लघुत्तम", "हर", "अंश"],
        "misconceptions": [
            {"id": "frac_add_across", "label": "Adds tops and bottoms",
             "description": "Adds numerators together and denominators together "
                            "(1/2 + 1/3 = 2/5)."},
            {"id": "frac_denominator_only", "label": "Changes denominators only",
             "description": "Rewrites with a common denominator but leaves the numerators "
                            "unchanged (1/2 + 1/3 = 1/6 + 1/6)."},
            {"id": "frac_keep_denominator", "label": "Keeps one denominator",
             "description": "Adds the numerators and keeps one of the denominators even when "
                            "they differ (1/2 + 1/4 = 2/4)."},
        ],
        "questions": [
            {"id": "fa1", "answer": "3/4",
             "en": "What is 1/2 + 1/4? Explain each step.",
             "hi": "1/2 + 1/4 कितना होता है? हर कदम समझाओ।"},
            {"id": "fa2", "answer": "5/6",
             "en": "What is 1/2 + 1/3? Tell me how you did it.",
             "hi": "1/2 + 1/3 कितना होता है? बताओ तुमने कैसे किया।"},
        ],
    },
]

SKILL_BY_ID = {s["id"]: s for s in SKILLS}
MISCONCEPTION_BY_ID = {m["id"]: {**m, "skill": s["id"]} for s in SKILLS for m in s["misconceptions"]}


def get_skill(skill_id):
    return SKILL_BY_ID.get(skill_id)


def get_question(skill_id, question_id):
    skill = SKILL_BY_ID.get(skill_id)
    if not skill:
        return None
    return next((q for q in skill["questions"] if q["id"] == question_id), None)


def misconception_label(mc_id):
    mc = MISCONCEPTION_BY_ID.get(mc_id)
    return mc["label"] if mc else mc_id
