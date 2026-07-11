"""
Neo4j Cypher 查询模板 & Schema 常量
"""

# === 节点标签 ===
PAPER = "Paper"
METHOD = "Method"
DATASET = "Dataset"
ARCHITECTURE = "Architecture"
METRIC = "Metric"
CONCEPT = "Concept"
AUTHOR = "Author"
CODE_REPO = "CodeRepository"
ENTITY_TAGS = [PAPER, METHOD, DATASET, ARCHITECTURE, METRIC, CONCEPT, AUTHOR, CODE_REPO]

# === 关系类型 ===
PROPOSES = "PROPOSES"            # (Paper)-[:PROPOSES]->(Method)
USES = "USES"                    # (Method)-[:USES]->(Dataset)
ACHIEVES = "ACHIEVES"            # (Method)-[:ACHIEVES]->(Metric)
COMPOSED_OF = "COMPOSED_OF"      # (Method)-[:COMPOSED_OF]->(Concept)
BASED_ON = "BASED_ON"            # (Method)-[:BASED_ON]->(Method)
OUTPERFORMS = "OUTPERFORMS"      # (Method)-[:OUTPERFORMS]->(Method)
CITES = "CITES"                  # (Paper)-[:CITES]->(Paper)
EVALUATES_ON = "EVALUATES_ON"   # (Paper)-[:EVALUATES_ON]->(Dataset)

RELATION_TYPES = [
    PROPOSES, USES, ACHIEVES, COMPOSED_OF, BASED_ON, OUTPERFORMS, CITES, EVALUATES_ON,
]

# === Schema 初始化 ===
INIT_SCHEMA_CYPHER = """
// 创建节点唯一性约束
CREATE CONSTRAINT IF NOT EXISTS FOR (p:Paper) REQUIRE p.arxiv_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (m:Method) REQUIRE m.name IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (d:Dataset) REQUIRE d.name IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (a:Architecture) REQUIRE a.name IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (m:Metric) REQUIRE m.name IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (c:Concept) REQUIRE c.name IS UNIQUE;

// 索引
CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name);
"""

# === 常用查询模板 ===

# 查询某数据集上各方法的指标
METHODS_ON_DATASET_CYPHER = """
MATCH (d:Dataset {name: $dataset})<-[:USES]-(m:Method)
OPTIONAL MATCH (m)-[:ACHIEVES]->(metric:Metric)
WHERE metric.name CONTAINS $metric_name
RETURN m.name AS method, collect(metric.name) AS metrics, collect(metric.value) AS values
ORDER BY m.name
"""

# 查询某概念相关的所有方法
METHODS_BY_CONCEPT_CYPHER = """
MATCH (c:Concept {name: $concept})<-[:COMPOSED_OF]-(m:Method)
OPTIONAL MATCH (m)<-[:PROPOSES]-(p:Paper)
OPTIONAL MATCH (m)-[:USES]->(d:Dataset)
RETURN m.name AS method,
       collect(DISTINCT p.title) AS papers,
       collect(DISTINCT d.name) AS datasets
"""

# 查询与某方法关联的实体路径
RELATIONS_AROUND_METHOD_CYPHER = """
MATCH (m:Method {name: $method_name})-[r]-(connected)
RETURN m.name AS source,
       type(r) AS relation,
       connected.name AS target,
       labels(connected)[0] AS target_type
LIMIT 50
"""
