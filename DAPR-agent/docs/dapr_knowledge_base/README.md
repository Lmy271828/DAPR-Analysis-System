# DAPR 结构化知识库

> 本知识库为 DAPR-Analysis-System 的 DAPR（雨中人）绘画分析提供理论支撑与伦理护栏。  
> 定位：**参考性知识库**，非诊断标准。系统中所有 DAPR 分析均定位为"艺术表达引导"，禁止临床诊断。  
> 维护：人工整理，版本控制，变更需评审。

## 目录

| 文件 | 内容 | 对系统的价值 |
|------|------|------------|
| [01_theoretical_framework.md](01_theoretical_framework.md) | DAPR 理论基础、起源、核心理论假设 | 帮助系统理解 DAPR 的设计初衷，避免偏离表达性艺术的定位 |
| [02_scoring_systems.md](02_scoring_systems.md) | 主要评分体系概览 | 了解学术界的量化尝试，但系统本身不使用评分 |
| [03_cultural_adaptation.md](03_cultural_adaptation.md) | 跨文化差异数据 | 避免文化误读，不同文化背景用户的解释校准 |
| [04_age_guidelines.md](04_age_guidelines.md) | 年龄相关解释校准 | 儿童/青少年/成人/老年的不同解释标准 |
| [05_ethical_guardrails.md](05_ethical_guardrails.md) | 伦理护栏：效度争议、过度解释风险 | **最重要**。明确系统"不该说什么"的知识依据 |
| [06_formal_elements.md](06_formal_elements.md) | 艺术元素分析维度详解 | 丰富观察角度，提升分析深度 |
| [07_ai_assessment_frontier.md](07_ai_assessment_frontier.md) | AI 辅助分析前沿研究 | 了解领域内技术标杆和最佳实践 |

## 使用方式

当前阶段（Phase 2），知识库以**静态 Markdown**形式存在，由开发者在 `prompts.py` 中根据用户画像（如年龄）选择性注入关键片段。不引入自动向量检索。

## 资料来源

本知识库内容来自以下文献的综合整理：

- Verinis, J. S., Lichtenberg, E. F., & Henrich, L. (1974). The Draw-A-Person in the rain technique. *Journal of Clinical Psychology, 30*, 407-414.
- Lack, H. (1996). *The Person-in-the-Rain Projective Drawing as a Measure of Children's Coping Capacity*. Master's Thesis, California School of Professional Psychology.
- Graves, J., Jones, C., & Kaplan, D. (2013). Construct validity of the Draw-A-Person-in-the-Rain assessment. *Art Therapy, 30*(3), 107-113.
- Tanaka, S. & Sato, A. (2024). Elementary Schoolchildren's Perspectives in the Draw-a-Person-in-the-Rain Test. *Psychology, 15*(5).
- Kim, J. et al. (2023). AlphaDAPR: An AI-based Explainable Expert Support System for Art Therapy. *ACM IUI*.
- Kang, J. et al. (2024). SceneDAPR: A Scene-Level Free-Hand Drawing Dataset for Web-based Psychological Drawing Assessment. *ACM WWW*.
- Kim, J. et al. (2025). CheckDAPR: An MLLM-based Sketch Analysis System for Art Therapy. *ACM CIKM*.
- 刘伟, 刘一格 (2022). 《雨中人画投射测验全息分析理论和技术》. 江苏大学出版社.
- Hirota, A. & Hirano, M. (2023). 雨中人物画テストの描き手の語りの理解. お茶の水女子大学.
- Oster, G. D. & Crone, P. G. (2004). *Using drawings in assessment and therapy*. Brunner-Routledge.
