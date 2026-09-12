"""The todo list, at the storage seam."""

from elcheapo.store.memory import InMemoryRepository


def a_repository() -> InMemoryRepository:
    return InMemoryRepository(categories=["Groceries"])


def test_a_new_user_has_no_tasks():
    assert a_repository().tasks() == []


def test_an_added_task_comes_back():
    repository = a_repository()

    repository.add_task("buy milk")

    assert [task.task for task in repository.tasks()] == ["buy milk"]


def test_an_added_task_is_given_an_id():
    repository = a_repository()

    added = repository.add_task("buy milk")

    assert added.task_id


def test_two_tasks_do_not_share_an_id():
    """The id is how the agent says which task it means."""
    repository = a_repository()

    first = repository.add_task("buy milk")
    second = repository.add_task("buy milk")

    assert first.task_id != second.task_id


def test_a_new_task_starts_incomplete():
    repository = a_repository()

    assert repository.add_task("buy milk").is_complete is False


def test_tasks_come_back_oldest_first():
    """A todo list reads top to bottom in the order things were added."""
    repository = a_repository()
    repository.add_task("buy milk")
    repository.add_task("call the vet")

    assert [task.task for task in repository.tasks()] == ["buy milk", "call the vet"]


def test_completing_a_task_marks_it_complete():
    repository = a_repository()
    added = repository.add_task("buy milk")

    repository.update_task(added.task_id, is_complete=True)

    assert repository.tasks(include_complete=True)[0].is_complete is True


def test_a_completed_task_drops_off_the_list_by_default():
    repository = a_repository()
    added = repository.add_task("buy milk")

    repository.update_task(added.task_id, is_complete=True)

    assert repository.tasks() == []


def test_a_completed_task_can_still_be_asked_for():
    repository = a_repository()
    added = repository.add_task("buy milk")
    repository.update_task(added.task_id, is_complete=True)

    assert len(repository.tasks(include_complete=True)) == 1


def test_a_completed_task_can_be_reopened():
    repository = a_repository()
    added = repository.add_task("buy milk")
    repository.update_task(added.task_id, is_complete=True)

    repository.update_task(added.task_id, is_complete=False)

    assert len(repository.tasks()) == 1


def test_editing_a_task_changes_its_words():
    repository = a_repository()
    added = repository.add_task("buy milk")

    repository.update_task(added.task_id, task="buy oat milk")

    assert repository.tasks()[0].task == "buy oat milk"


def test_editing_the_words_leaves_the_task_open():
    repository = a_repository()
    added = repository.add_task("buy milk")

    repository.update_task(added.task_id, task="buy oat milk")

    assert repository.tasks()[0].is_complete is False


def test_updating_a_task_that_is_not_there_says_so():
    repository = a_repository()

    assert repository.update_task("no-such-id", is_complete=True) is None


def test_an_update_touches_updated_at():
    repository = a_repository()
    added = repository.add_task("buy milk")

    updated = repository.update_task(added.task_id, is_complete=True)

    assert updated.updated_at >= added.created_at


def test_one_users_tasks_are_not_anothers():
    """Every read is scoped to one chat, as expenses are."""
    mine, theirs = a_repository(), a_repository()

    mine.add_task("buy milk")

    assert theirs.tasks() == []
