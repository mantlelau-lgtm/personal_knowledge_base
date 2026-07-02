请从下面 Markdown 文档片段中抽取结构化知识，必须只输出 JSON，不要 Markdown。

JSON 字段必须包含：
- summary：字符串
- concepts：数组，每项包含 name、description
- entities：数组，每项包含 name、type
- decisions：数组，每项包含 what、why、when
- action_items：数组，每项包含 task、owner、due
- claims：数组，每项包含 text、evidence
- topics：字符串数组
- connections：数组，每项包含 source、target、relation

文档片段：
{{text}}
