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


if __name__ == "__main__":
    app()
