"""A minimal multi-schema QuerySpace pipeline integration test."""

from querysmith import (
    ColumnSpec,
    ExecutionPolicy,
    RelationshipSpec,
    ResolvedQuerySpace,
    TableRef,
    TableSpec,
    ask,
)


class CapturingClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompt = ""

    def complete(self, prompt: str) -> str:
        self.prompt = prompt
        return self.response


def test_multi_schema_query_space_flows_through_serializer_llm_and_guard() -> None:
    person = TableSpec(
        TableRef("Person", "Person"),
        [ColumnSpec("BusinessEntityID", "int", False)],
    )
    employee = TableSpec(
        TableRef("HumanResources", "Employee"),
        [ColumnSpec("BusinessEntityID", "int", False)],
    )
    activity = TableSpec(
        TableRef("Activity", "PersonActivity"),
        [
            ColumnSpec("PersonID", "int", False),
            ColumnSpec("ActivityDate", "datetime2", False),
        ],
    )
    customer = TableSpec(
        TableRef("Sales", "Customer"),
        [ColumnSpec("PersonID", "int", False)],
    )
    relationships = [
        RelationshipSpec(
            employee.ref,
            "BusinessEntityID",
            person.ref,
            "BusinessEntityID",
        ),
        RelationshipSpec(
            activity.ref,
            "PersonID",
            person.ref,
            "BusinessEntityID",
        ),
        RelationshipSpec(
            customer.ref,
            "PersonID",
            person.ref,
            "BusinessEntityID",
        ),
    ]
    query_space = ResolvedQuerySpace(
        tables=[person, employee, activity, customer],
        relationships=relationships,
        execution_policy=ExecutionPolicy(max_rows=50),
    )
    client = CapturingClient(
        "SELECT a.PersonID, a.ActivityDate "
        "FROM Activity.PersonActivity AS a "
        "JOIN Person.Person AS p ON p.BusinessEntityID = a.PersonID "
        "JOIN HumanResources.Employee AS e "
        "ON e.BusinessEntityID = p.BusinessEntityID "
        "JOIN Sales.Customer AS c ON c.PersonID = p.BusinessEntityID"
    )

    sql = ask(
        question=("Show the latest activities for employees who are also customers."),
        query_space=query_space,
        client=client,
    )

    assert sql.startswith("SELECT TOP 50 a.PersonID")
    for full_name in (
        "Person.Person",
        "HumanResources.Employee",
        "Activity.PersonActivity",
        "Sales.Customer",
    ):
        assert full_name in client.prompt
