import threading

import fakeredis
import pytest

from shared.abstractions.memory import MAX_HISTORY_LIMIT, Message
from shared.memory import InMemoryStore, RedisMemoryStore, create_memory_store
from shared.memory import context_keys as K


@pytest.fixture(params=["in_memory", "redis", "redis_decoded"])
def store(request):
    if request.param == "in_memory":
        return InMemoryStore()
    server = fakeredis.FakeServer()
    return RedisMemoryStore(
        fakeredis.FakeStrictRedis(server=server, decode_responses=request.param == "redis_decoded")
    )


def msg(text, role="user", agent=None):
    return Message(role=role, content=text, agent_name=agent)


# ---- conversation ---------------------------------------------------------
def test_create_and_load_conversation(store):
    s = store.create_conversation("U1")
    store.append_message(s.conversation_id, Message("user", "xin chào", metadata={"k": "v"}), user_id="U1")
    loaded = store.get_conversation(s.conversation_id, user_id="U1")
    assert loaded.user_id == "U1"
    assert loaded.conversation_id == s.conversation_id
    assert [m.content for m in loaded.messages] == ["xin chào"]
    assert loaded.messages[0].metadata == {"k": "v"}


def test_get_missing_conversation_returns_none(store):
    assert store.get_conversation("khong-co") is None
    assert store.get_history("khong-co") == []
    assert store.get_messages("khong-co") == []


def test_append_to_missing_conversation_raises(store):
    with pytest.raises(KeyError):
        store.append_message("khong-co", msg("x"))


def test_unicode_content_roundtrip(store):
    s = store.create_conversation("U1")
    store.append_message(s.conversation_id, msg("Nguyễn Văn Ánh ở phòng Kế toán"))
    assert store.get_history(s.conversation_id)[0].content == "Nguyễn Văn Ánh ở phòng Kế toán"


def test_delete_conversation(store):
    s = store.create_conversation("U1")
    assert store.delete_conversation(s.conversation_id, user_id="U1") is True
    assert store.get_conversation(s.conversation_id) is None
    assert store.list_conversations("U1") == []
    assert store.delete_conversation(s.conversation_id) is False


def test_list_conversations_only_own_and_newest_first(store):
    a = store.create_conversation("U1")
    b = store.create_conversation("U1")
    store.create_conversation("U2")
    store.append_message(a.conversation_id, msg("cập nhật a"))  # a mới hơn b
    ids = [x.conversation_id for x in store.list_conversations("U1")]
    assert ids == [a.conversation_id, b.conversation_id]
    assert all(x.messages == [] for x in store.list_conversations("U1"))


# ---- history --------------------------------------------------------------
def test_history_limit_returns_latest_in_order(store):
    s = store.create_conversation("U1")
    for i in range(15):
        store.append_message(s.conversation_id, msg(f"m{i}"))
    assert [m.content for m in store.get_history(s.conversation_id)] == [f"m{i}" for i in range(5, 15)]
    assert [m.content for m in store.get_history(s.conversation_id, limit=3)] == ["m12", "m13", "m14"]
    assert len(store.get_messages(s.conversation_id)) == 15


def test_history_limit_validation_and_cap(store):
    s = store.create_conversation("U1")
    for i in range(MAX_HISTORY_LIMIT + 20):
        store.append_message(s.conversation_id, msg(f"m{i}"))
    with pytest.raises(ValueError):
        store.get_history(s.conversation_id, limit=0)
    assert len(store.get_history(s.conversation_id, limit=10_000)) == MAX_HISTORY_LIMIT


# ---- phân biệt user -------------------------------------------------------
def test_user_cannot_access_other_users_conversation(store):
    s = store.create_conversation("U1")
    store.append_message(s.conversation_id, msg("bí mật của U1"), user_id="U1")
    assert store.get_conversation(s.conversation_id, user_id="U2") is None
    assert store.get_history(s.conversation_id, user_id="U2") == []
    assert store.get_messages(s.conversation_id, user_id="U2") == []
    with pytest.raises(KeyError):
        store.append_message(s.conversation_id, msg("xâm nhập"), user_id="U2")
    assert store.delete_conversation(s.conversation_id, user_id="U2") is False
    assert len(store.get_messages(s.conversation_id, user_id="U1")) == 1


def test_user_context_isolated_between_users(store):
    store.update_user_context("U1", {K.LAST_EMPLOYEE_ID: "NV001"})
    assert store.get_user_context("U1") == {K.LAST_EMPLOYEE_ID: "NV001"}
    assert store.get_user_context("U2") == {}


# ---- context chung / riêng agent -----------------------------------------
def test_user_context_merges(store):
    store.update_user_context("U1", {"a": 1})
    store.update_user_context("U1", {"b": {"x": [1, 2]}, "a": 2})
    assert store.get_user_context("U1") == {"a": 2, "b": {"x": [1, 2]}}


def test_agent_context_separated_from_user_and_other_agents(store):
    store.update_user_context("U1", {"shared": True})
    store.update_agent_context("U1", "attendance", {K.LAST_MONTH: "2026-09"})
    store.update_agent_context("U1", "hiring", {"job": "Dev"})
    assert store.get_agent_context("U1", "attendance") == {K.LAST_MONTH: "2026-09"}
    assert store.get_agent_context("U1", "hiring") == {"job": "Dev"}
    assert store.get_agent_context("U1", "employee") == {}
    assert store.get_agent_context("U2", "attendance") == {}
    assert store.get_user_context("U1") == {"shared": True}


def test_context_survives_conversation_delete(store):
    s = store.create_conversation("U1")
    store.update_user_context("U1", {"x": 1})
    store.delete_conversation(s.conversation_id)
    assert store.get_user_context("U1") == {"x": 1}


def test_returned_data_is_a_copy(store):
    store.update_user_context("U1", {"nested": {"a": 1}})
    ctx = store.get_user_context("U1")
    ctx["nested"]["a"] = 999
    assert store.get_user_context("U1") == {"nested": {"a": 1}}


def test_empty_update_is_noop(store):
    store.update_user_context("U1", {})
    assert store.get_user_context("U1") == {}


# ---- kịch bản "người đó" --------------------------------------------------
def test_pronoun_scenario(store):
    s = store.create_conversation("U1")
    store.append_message(s.conversation_id, msg("Tìm nhân viên Nguyễn Văn A"))
    store.update_user_context("U1", {K.LAST_EMPLOYEE_ID: "NV001"})
    store.append_message(s.conversation_id, msg("Tháng này người đó đi làm bao nhiêu ngày?"))
    assert store.get_user_context("U1")[K.LAST_EMPLOYEE_ID] == "NV001"


# ---- đồng thời ------------------------------------------------------------
def test_concurrent_appends_do_not_lose_messages(store):
    s = store.create_conversation("U1")

    def worker(n):
        for i in range(50):
            store.append_message(s.conversation_id, msg(f"{n}-{i}"))

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(store.get_messages(s.conversation_id)) == 200


def test_concurrent_context_updates_different_keys(store):
    def worker(n):
        for i in range(20):
            store.update_user_context("U1", {f"k{n}_{i}": i})

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(store.get_user_context("U1")) == 80


# ---- riêng Redis ----------------------------------------------------------
def make_redis(**kw):
    client = fakeredis.FakeStrictRedis(server=fakeredis.FakeServer())
    return client, RedisMemoryStore(client, **kw)


def test_redis_conversation_ttl_refreshed_on_append():
    client, store = make_redis(conversation_ttl_seconds=100)
    s = store.create_conversation("U1")
    store.append_message(s.conversation_id, msg("hi"))
    assert 0 < client.ttl(f"conversation:{s.conversation_id}:meta") <= 100
    assert 0 < client.ttl(f"conversation:{s.conversation_id}:messages") <= 100


def test_redis_context_has_no_ttl_by_default_and_optional_ttl():
    client, store = make_redis()
    store.update_user_context("U1", {"a": 1})
    assert client.ttl("user_context:U1") == -1  # không hết hạn
    client2, store2 = make_redis(context_ttl_seconds=50)
    store2.update_user_context("U1", {"a": 1})
    assert 0 < client2.ttl("user_context:U1") <= 50


def test_redis_list_conversations_cleans_expired():
    client, store = make_redis()
    s = store.create_conversation("U1")
    client.delete(f"conversation:{s.conversation_id}:meta")  # giả lập hết hạn
    assert store.list_conversations("U1") == []
    assert client.zcard("user_conversations:U1") == 0


# ---- factory --------------------------------------------------------------
def test_factory_in_memory_default(monkeypatch):
    monkeypatch.delenv("MEMORY_PROVIDER", raising=False)
    assert isinstance(create_memory_store(), InMemoryStore)


def test_factory_reads_env(monkeypatch):
    monkeypatch.setenv("MEMORY_PROVIDER", "redis")
    client = fakeredis.FakeStrictRedis(server=fakeredis.FakeServer())
    assert isinstance(create_memory_store(redis_client=client), RedisMemoryStore)


def test_factory_unknown_provider():
    with pytest.raises(ValueError):
        create_memory_store("mongodb")
