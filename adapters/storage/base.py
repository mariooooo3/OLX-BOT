from abc import ABC, abstractmethod


class BaseStorageAdapter(ABC):
    """Contract pentru orice adaptor de stocare (JSON in MVP1, DB in MVP2)."""

    @abstractmethod
    def get_products(self) -> list:
        pass

    @abstractmethod
    def log_conversation(self, conversation: dict) -> None:
        pass

    @abstractmethod
    def is_processed(self, olx_conversation_id: str, buyer_message: str) -> bool:
        """True daca ULTIMUL mesaj procesat in conversatie e identic cu cel
        curent. Botul raspunde la fiecare mesaj nou dintr-o conversatie
        (inclusiv intrebari de continuare), dar nu de doua ori la acelasi."""

    @abstractmethod
    def mark_conversation_status(
        self, olx_conversation_id: str, buyer_message: str, status: str
    ) -> None:
        """Actualizeaza ultima incercare pentru mesaj la pending/sent/failed."""


class BaseJobQueue(ABC):
    """Contract pentru coada de joburi (MVP2 — scalare cu workeri separati).

    Un mesaj nou = un job. Producatorul (bucla de polling) face enqueue;
    unul sau mai multi workeri fac claim_next -> genereaza raspunsul ->
    complete; procesul cu browser trimite apoi raspunsurile 'done'.
    """

    @abstractmethod
    def enqueue_job(
        self,
        olx_conversation_id: str,
        buyer_message: str,
        buyer_name: str | None = None,
        ad_title: str | None = None,
    ) -> str:
        """Adauga un job nou (status=pending). Returneaza id-ul jobului.

        buyer_name si ad_title vin din antetul conversatiei OLX; ad_title
        identifica produsul discutat (potrivire stricta pe titlu)."""

    @abstractmethod
    def has_active_job(self, olx_conversation_id: str) -> bool:
        """True daca exista deja un job neterminat pentru conversatie
        (evita dublarea la enqueue)."""

    @abstractmethod
    def claim_next_job(self) -> dict | None:
        """Ia atomic urmatorul job pending (pending -> processing).
        Returneaza dict-ul jobului sau None daca coada e goala."""

    @abstractmethod
    def complete_job(self, job_id: str, response_text: str, product_id: str | None) -> None:
        """Marcheaza jobul rezolvat de worker (processing -> done)."""

    @abstractmethod
    def fail_job(self, job_id: str, error: str) -> None:
        """Marcheaza jobul esuat (-> failed, incrementeaza attempts)."""

    @abstractmethod
    def claim_job_to_send(self) -> dict | None:
        """Ia atomic urmatorul job gata de trimis (done -> sending)."""

    @abstractmethod
    def mark_job_sent(self, job_id: str) -> None:
        """Marcheaza jobul trimis pe OLX (sending -> sent)."""
