from rag_chat.postprocess import ContextCompressor, PostProcessor, Reranker
from rag_chat.retriever import SearchResult


def _result(doc_id: str, title: str, snippet: str, score: float, heading: str = "") -> SearchResult:
    return SearchResult(
        doc_id=doc_id,
        path=f"/path/{doc_id}",
        title=title,
        score=score,
        snippet=snippet,
        heading=heading,
    )


def test_rerank_changes_order(settings):
    reranker = Reranker(settings=settings)
    results = [
        _result("1", "历史地理", "历史地理天文气象知识概述", 1.0, heading="地理"),
        _result("2", "Python 测试", "python pytest testing framework 实践", 0.4, heading="测试"),
    ]
    reranked = reranker.rerank("python pytest testing", results, top_k=2)

    # result2 与 query 语义相似度更高，综合分数应超过 result1
    assert reranked[0].doc_id == "2"
    assert reranked[1].doc_id == "1"
    # 分数已被更新为融合后的综合分数
    assert reranked[0].score > reranked[1].score
    assert reranked[0].score != results[1].score


def test_rerank_empty_results(settings):
    reranker = Reranker(settings=settings)
    assert reranker.rerank("query", [], top_k=5) == []


def test_rerank_top_k_limit(settings):
    reranker = Reranker(settings=settings)
    results = [
        _result("1", "a", "python pytest testing one", 0.1),
        _result("2", "b", "python pytest testing two", 0.2),
        _result("3", "c", "python pytest testing three", 0.3),
    ]
    reranked = reranker.rerank("python pytest testing", results, top_k=2)
    assert len(reranked) == 2


def test_compress_dedup(settings):
    compressor = ContextCompressor()
    results = [
        _result("1", "标题一", "内容片段 A", 0.5, heading="章节一"),
        _result("2", "标题二", "内容片段 A", 0.4, heading="章节二"),
        _result("3", "标题三", "内容片段 B", 0.3, heading="章节三"),
    ]
    text = compressor.compress(results)
    # snippet 完全相同的第一条被保留，第二条去重
    assert text.count("内容片段 A") == 1
    assert text.count("内容片段 B") == 1
    # 去重后重新编号
    assert "[0]" in text
    assert "[1]" in text
    assert "[2]" not in text


def test_compress_truncate(settings):
    compressor = ContextCompressor()
    results = [
        _result("1", "标题一", "内容片段 A 较长一点", 0.5, heading="章节一"),
        _result("2", "标题二", "内容片段 B 较长一点", 0.4, heading="章节二"),
        _result("3", "标题三", "内容片段 C 较长一点", 0.3, heading="章节三"),
    ]
    text = compressor.compress(results, max_chars=40)
    # 截断后总长不超过 max_chars
    assert len(text) <= 40
    # 只保留能完整放下的条目，至少包含第一个
    assert "[0]" in text


def test_postprocessor_end_to_end(settings):
    processor = PostProcessor(settings=settings)
    results = [
        _result("1", "历史地理", "历史地理天文气象知识概述", 1.0, heading="地理"),
        _result("2", "Python 测试", "python pytest testing framework 实践", 0.4, heading="测试"),
        _result("3", "Python 测试副本", "python pytest testing framework 实践", 0.3, heading="测试"),
    ]
    reranked, context = processor.process(
        "python pytest testing", results, top_k=3, max_chars=4000
    )

    # rerank 后语义相关项排在前面
    assert reranked
    assert reranked[0].doc_id == "2"
    # 返回数量不超过 top_k
    assert len(reranked) <= 3
    # context 为非空字符串
    assert context
    # 去重生效：重复 snippet 只出现一次
    assert context.count("python pytest testing framework 实践") == 1
