"""Command-line interface for the walking skeleton.

    python -m app.cli ingest path/to/book.pdf --title "Physics Part 1" --grade 9
    python -m app.cli ask "What is Newton's first law?" --grade 9
    python -m app.cli docs
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Educator CLI — ingest books and ask questions.")
console = Console()


@app.command()
def ingest(
    file: Path = typer.Argument(..., exists=True, readable=True, help="Path to the document"),
    title: str = typer.Option(None, help="Document title (defaults to the file name)"),
    subject: str = typer.Option(None, help="Subject, e.g. Physics"),
    grade: str = typer.Option(None, help="Grade/class, e.g. 9"),
    language: str = typer.Option("en", help="en | hi | mixed"),
) -> None:
    """Parse, chunk, embed, and store a document."""
    from app.db import get_session_factory, init_db
    from app.models import Document, DocumentStatus
    from app.services.ingestion.pipeline import ingest_document

    init_db()
    db = get_session_factory()()
    document = Document(
        title=title or file.stem,
        subject=subject,
        grade=grade,
        language=language,
        file_path=str(file.resolve()),
        file_type=file.suffix.lower().lstrip("."),
        status=DocumentStatus.queued,
    )
    db.add(document)
    db.commit()

    console.print(f"Ingesting [bold]{document.title}[/bold] (document {document.id})…")
    ingest_document(db, document.id)
    chunk_count = len(document.chunks)
    console.print(f"[green]Done[/green] — {chunk_count} chunks stored.")


@app.command()
def ask(
    question: str = typer.Argument(..., help="The question to answer"),
    grade: str = typer.Option(None, help="Restrict to a grade"),
    subject: str = typer.Option(None, help="Restrict to a subject"),
) -> None:
    """Ask a question against the ingested books."""
    from app.db import get_session_factory
    from app.services.qa import answer_question

    db = get_session_factory()()
    with console.status("Thinking…"):
        result = answer_question(db, question, grade=grade, subject=subject)

    console.print(f"\n[bold]Answer:[/bold]\n{result.answer}\n")
    if result.sources:
        table = Table(title="Sources")
        table.add_column("#")
        table.add_column("Book")
        table.add_column("Subject")
        table.add_column("Page")
        for source in result.sources:
            table.add_row(
                str(source.index),
                source.document_title,
                source.subject or "-",
                str(source.page_number) if source.page_number else "-",
            )
        console.print(table)


@app.command()
def docs() -> None:
    """List ingested documents and their status."""
    from app.db import get_session_factory, init_db
    from app.models import Document

    init_db()
    db = get_session_factory()()
    table = Table(title="Documents")
    for column in ("ID", "Title", "Subject", "Grade", "Lang", "Type", "Status"):
        table.add_column(column)
    for doc in db.query(Document).order_by(Document.id).all():
        table.add_row(
            str(doc.id), doc.title, doc.subject or "-", doc.grade or "-",
            doc.language, doc.file_type, doc.status.value,
        )
    console.print(table)


@app.command()
def chat(
    grade: str = typer.Option(None, help="Restrict to a grade"),
    subject: str = typer.Option(None, help="Restrict to a subject"),
) -> None:
    """Interactive chat with conversation memory (streamed answers).

    Follow-up questions like "why is that?" are understood in context.
    Type 'exit' or press Ctrl+C to quit.
    """
    from app.db import get_session_factory, init_db
    from app.services import chat as chat_service

    init_db()
    db = get_session_factory()()
    conversation_id: int | None = None
    console.print("[dim]Chat started — ask away (type 'exit' to quit).[/dim]")

    while True:
        try:
            question = console.input("\n[bold cyan]You:[/bold cyan] ").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if not question or question.lower() in ("exit", "quit"):
            break

        console.print("[bold green]Tutor:[/bold green] ", end="")
        sources = []
        for event in chat_service.ask_stream(
            db, question, conversation_id=conversation_id, grade=grade, subject=subject
        ):
            if event["type"] == "start":
                conversation_id = event["conversation_id"]
            elif event["type"] == "token":
                print(event["text"], end="", flush=True)
            elif event["type"] == "done":
                sources = event["sources"]
        print()
        if sources:
            refs = ", ".join(
                f"[{s['index']}] {s['document_title']}"
                + (f" p.{s['page_number']}" if s["page_number"] else "")
                for s in sources
            )
            console.print(f"[dim]Sources: {refs}[/dim]")

    console.print("[dim]Bye![/dim]")


@app.command()
def quiz(
    grade: str = typer.Option(None, help="Restrict to a grade"),
    subject: str = typer.Option(None, help="Restrict to a subject"),
    num_questions: int = typer.Option(5, help="How many questions"),
) -> None:
    """Generate a quiz from the ingested books."""
    from app.db import get_session_factory, init_db
    from app.services.quiz import generate_quiz

    init_db()
    db = get_session_factory()()
    with console.status("Writing quiz…"):
        result = generate_quiz(db, grade=grade, subject=subject, num_questions=num_questions)

    if result.get("questions") is None:
        console.print(f"[red]Quiz failed:[/red] {result.get('error')}")
        if result.get("raw"):
            console.print(f"[dim]{result['raw']}[/dim]")
        raise typer.Exit(1)

    letters = "ABCD"
    for i, q in enumerate(result["questions"], start=1):
        console.print(f"\n[bold]Q{i}. {q['question']}[/bold]")
        for letter, option in zip(letters, q.get("options", [])):
            console.print(f"   {letter}) {option}")
        answer_index = q.get("answer_index", 0)
        answer_letter = letters[answer_index] if 0 <= answer_index < 4 else "?"
        console.print(f"   [green]Answer: {answer_letter}[/green]  [dim]{q.get('explanation', '')}[/dim]")


if __name__ == "__main__":
    app()
