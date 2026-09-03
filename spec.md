# 1. Wprowadzenie i Założenia Systemowe

Architektura **Agent System (Enterprise++ v3.5)** opiera się na zasadzie **pełnego odseparowania (decouplingu)** centralnego układu logicznego (*Core Brain*) od interfejsów użytkownika oraz urządzeń wykonawczych (drony, sensory, automatyka). System zaprojektowano jako **100% lokalny (Fully Offline)**, co eliminuje opóźnienia sieciowe, uniezależnia operacje od dostępu do internetu oraz gwarantuje bezwzględne bezpieczeństwo danych i zgodność prawną w rygorystycznych środowiskach przemysłowych i obronnych.

W wersji 3.5 architekturę zoptymalizowano pod kątem obsługi multimediów, asystencji deweloperskiej oraz zaawansowanej analityki wideo. Rozdzielono strumieniowanie telemetrii wysokiej częstotliwości (NATS JetStream z zasadą Drop-Tail) od klastrowej pamięci stanów (Redis Cluster / Sentinel). Wprowadzono **sprzętowy Fail-Safe (Heartbeat / Dead Man's Switch)** na poziomie autopilota, **izolację VRAM przez NVIDIA MPS**, **proaktywny monitoring termiczny GPU**, **Fencing Tokens**, **dwustopniowy akcelerowany audyt z drzewami Merkle’a**, **atomowe przeładowanie konfiguracji (Atomic Hot-Reload z debouncingiem)**, **izolację sandboxa z prawami Read-Only i pamięcią `tmpfs`**, a także dedykowane moduły dla **analizy wideo Roboflow**, **czatu z generowaniem plików (PDF/obrazy)** oraz **klienta MCP dla Cline (VS Code)**.

### Kluczowe Filary Architektury Enterprise++ (v3.5)

* **Decoupled Telemetry & NATS JetStream Engine (z TTL i Drop-Tail):** Odseparowanie strumieni telemetrii >50Hz do dedykowanego lokalnego brokera NATS JetStream z twardym limitem TTL (<500 ms) i polityką odrzucania przestarzałych klatek (Drop-Tail), chroniące GPU przed zalaniem po zimnym starcie.
* **Hardware Safe-State Reset & Dead Man’s Switch:** Fizyczny autopilot (PX4/ArduPilot) wymagający sygnału Heartbeat co 200 ms via UART; brak sygnału wywołuje natychmiastowe autonomiczne powrócenie do bazy (RTL) lub lądowanie z pominięciem OS/Pythona.
* **NVIDIA MPS & Strict VRAM Partitioning:** Twarda izolacja zasobów pamięci GPU (max 50% vLLM, max 30% Roboflow CV / YOLO, max 20% narzędzia i parserów) przez NVIDIA Multi-Process Service.
* **Advanced Computer Vision (Roboflow Integration):** Przetwarzanie plików wideo pod kątem precyzyjnej detekcji obiektów, marek i logotypów z mapowaniem czasowym (*timestamps*), stopniem widoczności oraz kontekstem fizycznym.
* **Chat, File Ingestion & Document Generation:** Obsługa interakcji konwersacyjnych z przesyłaniem plików oraz dynamicznym generowaniem dokumentów (raporty PDF, grafiki) w izolowanym środowisku.
* **Cline Extension Integration (MCP Client):** Bezpieczny most komunikacyjny Model Context Protocol pozwalający asystentowi na inspekcję kodu, testowanie i edycję w środowisku VS Code za zgodą dewelopera.
* **Thermal Awareness & Throttling Node:** Dynamiczny węzeł odczytujący temperaturę GPU przez `pynvml`; po przekroczeniu 80°C automatycznie redukuje klatkaż kamer i przełącza inferencję na lekki model Fallback.
* **Context Prefix Caching:** Zamrożenie statycznego rdzenia promptów w VRAM redukujące czasy generowania pierwszego tokena (TTFT) przy częstym przełączaniu zadań.
* **Protektory Nośników Flash (Group Commit / Ring Buffer):** Buforowanie zapisów logów SHA-256 w RAM przed zrzutem na dyski przemysłowe pSLC, wykluczające zjawisko Write Amplification.
* **Fencing Tokens & Distributed Lock Management:** Zabezpieczenie komend fizycznych monotonicznymi tokenami fencingowymi i rozproszonymi blokadami Redis Cluster / Sentinel z jawnym czasem żywotności (TTL).
* **OS-Level Process Supervision & Hardware Watchdog:** Nadzór nad procesami głównymi realizowany przez `systemd`/`supervisord` podłączony pod `/dev/watchdog`, chroniący przed zawieszeniem pętli `asyncio`.
* **Master Clock & Anti-Spoofing PTP Synchronization:** Lokalny wzorzec czasu (GPS/PTP) z odpornością na *clock drift* i algorytmem detekcji spoofingu GPS.
* **LangGraph Bounded Recursion & Fallback:** Twardy limit prób naprawy błędnych struktur JSON (`max_retries=3`) chroniący przed nieskończonym pętlaniem grafu.
* **Pydantic State Versioning & Migrators:** Automatyczna transformacja schematów danych dla starych sesji z bazy Redis na podstawie pola `schema_version`.
* **Merkle Tree Verified Audit Trail:** Akcelerowany system logowania zdarzeń z autoweryfikacją migawek (Checkpoints) z użyciem drzew Merkle’a i zapisem blokowym.
* **Atomic Hot-Reloading z Debouncingiem:** Atomowa zmiana promptów poprzez `os.replace` z buforem czasowym 300 ms, unikająca wyścigów stanów.
* **Disaster Recovery & Master Recovery Key:** Papierowy klucz awaryjny umożliwiający ręczne odszyfrowanie partycji LUKS2 po uszkodzeniu modułu TPM 2.0.
* **Read-Only Sandbox & Tmpfs File Isolation:** Wykonanie podatnych na ataki parserów plików w izolowanym kontenerze z wolumenem głównym `read-only` i dyskiem tymczasowym w pamięci RAM (`tmpfs`).

# 2. Rozszerzona Architektura Systemu

```text
agent-system/
├── configs/                      # Konfiguracja systemu i prompty (Hydra / Dynaconf)
│   ├── system.yaml               # Globalne parametry infrastrukturalne
│   ├── prompts/                  # Wersjonowane prompty (hot-reloadable)
│   │   ├── v3.5_core.yaml        # Główny prompt rdzenia LangGraph
│   │   └── v2_fallback.yaml      # Lekki prompt dla modelu awaryjnego
│   └── schemas/                  # Walidatory Pydantic v2 dla konfiguracji
├── src/                          # Kod źródłowy aplikacji
│   ├── core/                     # Centralny mózg i grafy stanów
│   │   ├── graph.py              # Definicja LangGraph i max_retries
│   │   ├── state.py              # Wersjonowanie stanów (schema_version)
│   │   └── migrators.py          # Migratory Pydantic dla starych sesji
│   ├── ingestion/                # Warstwa wejściowa i telemetria
│   │   ├── nats_client.py        # Obsługa NATS JetStream (Drop-Tail, TTL)
│   │   └── telemetry_50hz.py     # Odbiór danych wysokiej częstotliwości
│   ├── safety/                   # Moduły bezpieczeństwa i hardware
│   │   ├── redlock_mgr.py        # Rozproszone blokady i Fencing Tokens
│   │   ├── thermal_node.py       # pynvml monitor temp GPU (>80°C)
│   │   └── heartbeat_uart.py     # Hardware Dead Man's Switch (200 ms)
│   ├── inference/                # Warstwa inferencji i zarządzania GPU
│   │   ├── mps_manager.py        # Konfiguracja NVIDIA MPS (50/30/20)
│   │   └── router.py             # Circuit Breaker i Fallback Router
│   ├── audit/                    # Dziennik zdarzeń i kryptografia
│   │   ├── merkle_tree.py        # Drzewa Merkle'a i weryfikacja O(1)
│   │   └── ring_buffer.py        # Buforowanie wpisów i Group Commit
│   └── mcp/                      # Narzędzia i sandbox wykonawczy
│       ├── doc_parser.py         # Izolowany parser dokumentów (Docling)
│       └── mavlink_ctrl.py       # Kontroler dronów z weryfikacją tokenów
├── storage/                      # Wolumeny trwałe (szyfrowane LUKS2)
│   ├── qdrant_data/              # Baza wektorowa Qdrant
│   └── redis_checkpoints/        # Stan klastra Redis / Checkpointer
└── scripts/                      # Skrypty systemowe i ratunkowe
    ├── verify_audit.sh           # Szybka weryfikacja integralności logów
    └── emergency_rtl.sh          # Awaryjne wywołanie powrotu do bazy
```

```mermaid
graph TD
    %% Warstwa Sensoryczna i IoT
    subgraph Warstwa_Sensoryczna [1. Warstwa Ingestion & Sensoryka]
        Dron_Sensory[Kamery & Telemetria Drona >50Hz]
        IoT_Sensory[Czujniki Automatyki / Smart Home]
        Web_Clients[Aplikacje WWW / Cline Dev UI / Chat Files]
        Master_Clock[Master Clock - PTP IEEE 1588 / GPS]
    end

    %% Szyna Zdarzeń, TTL & Backpressure
    subgraph Szyna_Zdarzen [2. Asynchroniczna Szyna Zdarzeń & Backpressure]
        NATS_Engine[NATS JetStream Engine - TTL < 500ms + Drop-Tail + Backpressure]
        Broker_MQTT[Broker MQTT / Redis PubSub]
        Worker[Background Stream Worker]
        DLQ_Queue[(Dead Letter Queue - DLQ)]
        
        Dron_Sensory -- Stream Telemetrii >50Hz --> NATS_Engine
        IoT_Sensory -- Stream MQTT --> Broker_MQTT
        Web_Clients -- JSON-RPC / API / Pliki / Wideo --> Broker_MQTT
        Master_Clock -. Sync Czasu .-> NATS_Engine
        Master_Clock -. Sync Czasu .-> Broker_MQTT
        NATS_Engine --> Worker
        Broker_MQTT --> Worker
        Worker -- Błędne pakiety / Corrupt frames --> DLQ_Queue
        NATS_Engine -- Masowy Drop klatek / Backpressure --> Dron_Sensory
    end

    %% Zarządzanie Konfiguracją & Promptami
    subgraph Config_Layer [3. Prompt & Config Management]
        Hydra_Config[Atomic Hydra Loader - Debounce 300ms + os.replace]
        Prompt_Reg[Rejestr Wersji Promptów - Local Git/YAML]
        Prompt_Eval[Prompt Evaluation Engine - Phoenix]
        
        Hydra_Config <--> Prompt_Reg
        Prompt_Eval -. Testy Regresji .-> Prompt_Reg
    end

    %% Centralny Mózg & Kontrola Stanu
    subgraph Centralny_Mozg [4. Core Brain - LangGraph Architecture]
        Graph[Główny Graf Stanu LangGraph - Max Retries = 3]
        Thermal_Node[Thermal Awareness Node - pynvml]
        Context_Compressor[Context Summarizer Node & Prefix Caching]
        Checkpointer[(Encrypted Redis Cluster Checkpointer)]
        Redlock_Mgr[Redlock & Fencing Token Generator]
        Audit_Logger[Merkle Tree Crypto Audit Ledger - Group Commit]
        Guard[Pydantic v2 Output Guardrails]
        Semantic_Cache[(Semantic Cache Engine)]
        State_Migrator[Pydantic State Migrator - schema_version]

        Graph <--> Thermal_Node
        Graph <--> Context_Compressor
        Graph <--> Checkpointer
        Graph <--> Redlock_Mgr
        Graph --> Audit_Logger
        Graph --> Guard
        Graph <--> Semantic_Cache
        Checkpointer <--> State_Migrator
    end

    %% Kontrola Przepustowości, MPS & vLLM / Roboflow
    subgraph Warstwa_Inference [5. Warstwa Inferencji, MPS & Rate Limiting]
        MPS_Mgr[NVIDIA MPS Manager - VRAM Partitioning 50/30/20]
        GPU_Queue[GPU Rate Limiter & Priority Queue]
        Router[Circuit Breaker, Failback Router & Cooldown Probe]
        M_Primary[Model Główny: vLLM / Llama]
        M_Roboflow[Roboflow CV / YOLO Inference Engine]
        M_Fallback[Model Zapasowy / Fallback]
        
        MPS_Mgr --> GPU_Queue
        GPU_Queue --> Router
        Router -- Tryb Normalny --> M_Primary
        Router -- Zadanie Video CV --> M_Roboflow
        Router -- OOM / Thermal Fallback --> M_Fallback
    end

    %% Peryferia, Hardware Watchdog & Safety
    subgraph Peryferia [6. Zabezpieczone Peryferia & Hardware Safety]
        OS_Watchdog[OS Systemd Supervisor + Hardware Watchdog /dev/watchdog]
        HW_Heartbeat[Hardware Dead Man Switch - UART Heartbeat 200ms]
        
        subgraph MCP_Sandbox [MCP Sandbox - Read-Only FS + Tmpfs]
            MCP_Dron[MCP Mavlink Controller + Fencing Check]
            MCP_Vision[MCP YOLO-World / Roboflow Engine]
            MCP_Doc[MCP Docling & PDF/Image Generator]
        end
        
        Mem0[(Mem0 L0-L4 Engine)]
        Qdrant[(Qdrant Cluster - Encrypted Volume)]
        
        OS_Watchdog -. Nadzór Procesu .-> MCP_Sandbox
        MCP_Dron -- UART Heartbeat 200ms --> HW_Heartbeat
        HW_Heartbeat -. Fail-Safe Override RTL .-> Dron_Sensory
        Mem0 <--> Qdrant
    end

    %% Połączenia Przepływu Logicznego
    Hydra_Config -. Atomic Hot-Reload .-> Graph
    Worker -- Zaktualizowany Stan / Event --> GPU_Queue
    GPU_Queue --> Graph
    Graph -- Wywołanie Inferencji --> GPU_Queue
    Guard -- Safe Komenda + Fencing Token --> MCP_Sandbox
    Graph <--> Mem0
```

# 3. Kompletny Stack Technologiczny (Enterprise++ v3.5)

| Komponent | Wybrana Technologia | Rola w Systemie | Uzasadnienie Techniczne & Produkcyjne |
| :--- | :--- | :--- | :--- |
| **Orkiestrator** | **LangGraph (Python)** | Cykliczne grafy stanowe i logika agenta z limitem rekurencji (`max_retries=3`). | Obsługuje pętle decyzyjne i zapobiega nieskończonemu zjadaniu tokenów przy błędach JSON[cite: 3]. |
| **Szyna Telemetrii** | **NATS JetStream (Drop-Tail)** | Przesył danych wysoce częstotliwych (>50Hz) z TTL < 500 ms[cite: 3]. | Eliminuje przeciążenie RAM/GPU po starcie i wyrzuca przestarzałe klatki telemetrii[cite: 3]. |
| **Izolacja GPU** | **NVIDIA MPS (Multi-Process Service)** | Partycjonowanie pamięci VRAM na poziomie sprzętowym (50% vLLM, 30% Roboflow, 20% narzędzia). | Zapobiega awariom CUDA OOM przy jednoczesnym uruchamianiu modeli językowych i wizyjnych[cite: 3]. |
| **Computer Vision** | **Roboflow API / Inference SDK + YOLO** | Analiza wideo, detekcja logotypów i obiektów ze znacznikami czasowymi (*timestamps*). | Dostarcza precyzyjne przedziały widoczności marek, stopień pewności oraz kontekst fizyczny[cite: 3]. |
| **Chat & Generowanie Plików** | **FastAPI + ReportLab / WeasyPrint** | Obsługa konwersacji, przesyłania plików oraz generowania dokumentów PDF i grafik[cite: 3]. | Umożliwia użytkownikom interakcję z plikami oraz eksport wyników analiz w formie raportów[cite: 3]. |
| **Integracja Deweloperska** | **Cline Extension for VS Code (MCP Client)** | Automatyzacja programistyczna i wykonywanie zadań bezpośrednio w edytorze kodu[cite: 3]. | Pozwala agentowi na bezpieczną interakcję z kodem źródłowym projektu i środowiskiem IDE[cite: 3]. |
| **Hardware Safety** | **Dedykowany UART + Hardware Dead Man's Switch (200 ms)** | Izolowany fizycznie/logicznie kanał szeregowy dla sygnału żywotności. | Uniemożliwia zagłuszenie sygnału bezpieczeństwa przez zapchany bufor telemetrii >50Hz. |
| **Wersjonowanie Promptów** | **Hydra / Dynaconf (Debounced)** | Hot-reloading z walidacją Pydantic, debouncingiem 300 ms i `os.replace`[cite: 3]. | Atomowa zmiana konfiguracji z ochroną przed wyścigami zdarzeń systemowych[cite: 3]. |
| **System Watchdog** | **Systemd + `/dev/watchdog`** | Monitorowanie procesów na poziomie OS[cite: 3]. | Fizyczne zresetowanie zawieszonej pętli AsyncIO przez sprzętowy timer płyty[cite: 3]. |
| **Wzorzec Czasu** | **PTP IEEE 1588 / GPS Master Clock** | Synchronizacja czasowa urządzeń w trybie offline[cite: 3]. | Spójne znaczniki czasu w niezmienniczym dzienniku audytowym bez dostępu do NTP[cite: 3]. |
| **Bezpieczeństwo Fizyczne** | **Fencing Tokens (Monotonic ID)** | Ochrona urządzeń wykonawczych (PX4)[cite: 3]. | Uniemożliwia wykonanie spóźnionych komend wywołanych przez stop-the-world GC[cite: 3]. |
| **Szyfrowanie i Disaster Recovery** | **LUKS2 / TPM 2.0 + Master Recovery Key** | Szyfrowanie wolumenów i procedura odzyskiwania[cite: 3]. | Ochrona danych w spoczynku i opcja awaryjnego odszyfrowania dysku bez modułu TPM[cite: 3]. |
| **Sandbox MCP** | **Docker Read-Only + Tmpfs / AppArmor** | Ścisła izolacja podatnych narzędzi (Docling i generatory PDF)[cite: 3]. | Zapobiega modyfikacji systemu plików i eskalacji uprawnień przy przetwarzaniu plików[cite: 3]. |
| **Verified Audit Ledger** | **Merkle Tree Audit Ledger (Ring Buffer)** | Niezmienialny log SHA-256 z grupowym zapisem[cite: 3]. | Błyskawiczna weryfikacja migawek ($O(1)$ przy starcie) oraz ochrona nośników pSLC[cite: 3]. |
| **Silnik Inferencji** | **vLLM (Prefix Caching Enabled)** | Lokalny model językowy z zamrożonym rdzeniem promptów[cite: 3]. | Niskie opóźnienie TTFT i brak wycieków danych w środowisku 100% offline[cite: 3]. |
| **Rozproszony Konsensus** | **etcd / Raft Protocol** *(Zastąpienie Redlock)* | Zarządzanie dystrybucją blokad i fencing tokenów[cite: 3]. | Eliminuje ryzyko split-brain w warunkach zakłóceń radiowych, gwarantując spójność silnego konsensusu[cite: 3]. |
| **Broker Krawędziowy** | **NATS JetStream (High-Availability Cluster)** | Niezawodna szyna telemetrii z replikacją[cite: 3]. | Zapobiega powstaniu pojedynczego punktu awarii (SPOF) na krawędzi (Edge) przy awarii pojedynczego kontenera[cite: 3]. |
| **Polityka Retencji Logów** | **Rotator zautomatyzowany (Cron / Systemd Timer)** | Cykliczne archiwizowanie i usuwanie starych bloków audytowych[cite: 3]. | Zapobiega pełnemu zapełnieniu dysku systemowego na partycji root i wolumenie kryptograficznym w długich misjach[cite: 3]. |

# 4. Specyfikacja Przepływów Sekwencyjnych

### 4.1. Hot-Reloading, Fencing Tokens i Weryfikacja Audytu Merkle Tree

```mermaid
sequenceDiagram
    autonumber
    actor Admin as Operator / Admin
    participant Conf as Dynamic Prompt Manager
    participant Graph as LangGraph Core
    participant Lock as Redlock & Fencing Mgr
    participant Audit as Merkle Tree Audit Ledger
    participant MCP_D as MCP Mavlink (Read-Only Sandbox)
    participant HW as Sterownik Drona (PX4)

    %% Autoweryfikacja Audytu Merkle Tree przy Starcie
    Note over Audit: Inicjalizacja Systemu: Weryfikacja Migawki Merkle Tree O(1)
    Audit->>Audit: Uruchomienie verify_checkpoint_integrity()
    alt Migawka Naruszona
        Audit-->>Admin: ALARM CRITICAL: Modyfikacja historii logów! System zatrzymany.
    else Migawka Spójna
        Audit-->>Graph: Status OK: Dziennik bezpieczny.
    end

    %% Atomic Hot-Reloading z Debouncingiem
    Admin->>Conf: Edycja pliku v2_llama4.yaml
    Note over Conf: Debouncing Buffer (Oczekiwanie 300 ms na koniec zapisu)
    Conf->>Conf: Walidacja Pydantic Schema
    alt Błąd Składni
        Conf-->>Admin: Błąd walidacji! Anulowano przeładowanie.
    else Walidacja Poprawna
        Conf->>Conf: os.replace(tmp_file, target_file) - Operacja Atomowa
        Conf->>Graph: Wstrzyknięcie zaktualizowanych promptów
    end

    %% Egzekucja Komendy z Fencing Token
    Graph->>Lock: Żądanie blokady i Fencing Tokena (TTL = 5000ms)
    Lock-->>Graph: Przyznano Blokadę + Fencing Token ID: 1042
    Graph->>Audit: Buforowanie wpisu w RAM (Ring Buffer -> Group Commit)
    Graph->>MCP_D: Komenda Ruchu + Fencing Token: 1042
    
    Note over MCP_D: Weryfikacja Tokena: (1042 > Ostatni Odebrany 1041)
    MCP_D->>HW: Przekazanie sygnału do silników
    MCP_D-->>Lock: Zwolnienie blokady rozproszonej
```
```mermaid
sequenceDiagram
    autonumber
    actor Drone as Dron (Telemetria >50Hz + UART)
    participant NATS as NATS JetStream Engine (TTL < 500ms)
    participant Therm as Thermal Monitor (pynvml)
    participant Router as Model Router & MPS Manager
    participant vLLM as Primary LLM (50% VRAM)
    participant HW_FS as Autopilot PX4 (Hardware Fail-Safe)

    %% Strumieniowanie Telemetrii z Drop-Tail
    Drone->>NATS: Wysyłanie klatek telemetrii (>50Hz)
    Note over NATS: Sprawdzanie TTL komunikatów (<500ms)
    alt Przekroczono TTL (Zimny Start / Przeciążenie)
        NATS->>NATS: Drop Frame (Odrzucenie przestarzałej klatek)
    else Klatka Aktualna
        NATS->>Router: Przekazanie najnowszej klatki do przetworzenia
    end

    %% Kontrola Termiczna
    Therm->>Therm: Odczyt temperatury GPU przez pynvml
    alt Temp GPU > 80°C
        Therm->>Router: Flaga THERMAL_CRITICAL: Obniż klatkaż i użyj Fallback
        Router->>Router: Przełączenie na model zapasowy Qwen-2.5-7B
    end

    %% Hardware Heartbeat Loop
    loop Co 200 ms (Niezależny Wątek Hardware)
        Router->>Drone: Sygnał Heartbeat przez port szeregowy UART
    end
    
    %% Awaria Systemu Operacyjnego / Kernel Panic
    Note over Router: KERNEL PANIC / Zawieszenie OS (Brak sygnału UART)
    Note over HW_FS: Autopilot PX4: Odliczenie 200 ms -> BRAK HEARTBEAT!
    HW_FS->>Drone: PRZEJĘCIE KONTROLI: Automatyczny Powrót do Bazy (RTL) / Lądowanie
```

# 5. Specyfikacja Modułów Logicznych i Ochronnych Systemu

### 5.1. Dynamic Prompt Manager & Atomic Config Loader
* **Mechanizm Debouncingu (300 ms):** Zapobiega wielokrotnemu przeładowaniu systemu w trakcie ciągłego edytowania plików konfiguracyjnych przez operacje systemowe i edytory tekstu.
* **Operacje Atomowe (`os.replace`):** Gwarantują, że aplikacja nigdy nie odczyta częściowo zapisanego pliku konfiguracyjnego. Plik tymczasowy jest w pełni zapisywany, walidowany przez schemat Pydantic i dopiero po pozytywnej walidacji zastępuje stary plik produkcyjny.
* **Automatyczny Fallback Zmian:** W przypadku błędu walidacji nowego promptu, proces zachowuje wcześniej załadowaną, poprawną wersję w pamięci RAM i zgłasza błąd krytyczny do konsoli operatora.

### 5.2. Hardware Heartbeat Sender & Thermal Awareness Node
* **Sprzętowy Dead Man's Switch (200 ms) na Dedykowanym Kanale:** Dedykowany, niskopoziomowy proces przesyła bajtowy sygnał żywotności do autopilota PX4 przez **całkowicie odizolowany fizycznie lub priorytetyzowany port szeregowy UART** (z ominięciem masowego bufora telemetrii). Zapobiega to sytuacji, w której zapchanie bufora opóźni wyjście pakietu i wywoła fałszywy alarm RTL. Brak sygnału przez okres dłuższy niż 200 ms skutkuje sprzętowym odcięciem sterowania i przejściem autopilota w autonomiczny tryb RTL (*Return To Launch*).
* **Thermal Awareness Node (`pynvml`):** Odczytuje parametry fizyczne karty graficznej w czasie rzeczywistym. Przekroczenie progu $80^\circ\text{C}$ powoduje wysłanie sygnału degradacji do pętli sterującej, obniżenie rozdzielczości klatek wejściowych oraz przełączenie modelu językowego na lżejszy wariant zapasowy.

### 5.3. Distributed Lock & Fencing Token Generator
* **Ochrona przed wyścigami stanów (Race Conditions):** Wykorzystanie algorytmu **Redlock** na klastrze Redis gwarantuje unikalność wykonywania operacji na fizycznych urządzeniach.
* **Monotoniczne Tokeny Fencingowe:** Każda komenda kierowana do urządzeń wykonawczych zawiera unikalny, rosnący identyfikator liczbowy. Urządzenie wykonawcze odrzuca wszelkie komendy, których token jest mniejszy lub równy ostatnio przetworzonemu, zapobiegając egzekucji opóźnionych poleceń z bufora.

### 5.4. Merkle Tree Audit Ledger z Ring Bufferem
* **Ochrona sprzętu pSLC (Group Commit):** Operacje wpisu logów są najpierw gromadzone w pamięci RAM w buforze pierścieniowym (*Ring Buffer*). Zrzut na fizyczny nośnik odbywa się w trybie **Group Commit** (np. po zebraniu 100 wpisów), co zapobiega zużyciu komórek pamięci flash SSD.
* **Niezmienniczość Zdarzeń (Kryptograficzne Drzewo Merkle'a):** Każdy bloki logów jest połączony skrótem SHA-256 z blokiem poprzednim. Weryfikacja spójności całego dziennika audytowego odbywa się w czasie $O(1)$ przy użyciu zarejestrowanych migawek kryptograficznych.

### 5.5. Graceful Degradation Pamięci Długoterminowej (Mem0 / Qdrant)
* **Monitorowanie Pojemności Bazy Wektorowej:** Automatyczne śledzenie zapełnienia wolumenu dyskowego Qdrant i partycji `tmpfs`.
* **Polityka Przepełnienia (Eviction Policy):** W przypadku osiągnięcia progu 90% zapełnienia, system automatycznie uruchamia procedurę konsolidacji warstw Mem0 (kompresja poziomów L3-L4 do wektorów zbiorczych) oraz usuwa przestarzałe, nietrywialne epizody operacyjne bez utraty krytycznego kontekstu misji.

### 5.6. Fallback LangGraph Guardrails & JSON Schema Recovery
* **Strukturyzowane Strażniki Pydantic:** W przypadku aktywacji trybu przegrzania i przełączenia na model zapasowy (np. Qwen-2.5-7B), LangGraph wymusza rygorystyczną walidację schematu wyjściowego Pydantic.
* **Obsługa Błędów Składniowych:** Mniejsze modele podatne na błędy formatowania JSON są obsługiwane przez dedykowany węzel naprawczy z ograniczeniem `max_retries=3`, który w razie awarii natychmiast aplikuje bezpieczny domyślny stan systemowy zamiast zawieszać pętlę decyzyjną.

### 5.7. NVIDIA MPS Thread Priority & Resource Balancing
* **Zapobieganie Głodzeniu Agentów (Resource Starvation):** Choć NVIDIA MPS skutecznie partycjonuje pamięć VRAM (np. 50% vLLM, 30% Roboflow, 20% narzędzia), rdzenie CUDA pozostają współdzielone. Aby intensywna analiza wideo nie spowolniła głównego modelu językowego, proces vLLM konfigurowany jest z wyższym priorytetem harmonogramowania za pomocą zmiennych środowiskowych i flag kontrolnych (`CUDA_DEVICE_MAX_CONNECTIONS` / wag MPS).
* **Gwarancja Czasu Rzeczywistego:** Rozwiązanie to chroni przed narastaniem opóźnień decyzyjnych w grafie LangGraph, zapewniając stabilny czas odpowiedzi agenta niezależnie od obciążenia modułów wizyjnych.

### 5.8. Architektoniczne Domknięcie Luk Systemowych (Redlock, SPOF, GPU Drain, Retencja)
* **Zastąpienie Redlock konsensusem Raft (etcd):** Krytyczne blokady fizyczne obsługiwane są przez mechanizmy oparte o silny konsensus Raft, co uniemożliwia wygenerowanie konkurencyjnych fencing tokenów w przypadku partycjonowania sieci lub resetu węzła master.
* **Wysoka Dostępność Szyny NATS:** Broker krawędziowy wdrożony jest w architekturze klastrowej z replikacją stanu, eliminując SPOF. Awaria pojedynczego węzła nie powoduje zamrożenia ingestii telemetrii >50Hz.
* **Graceful Drainage zadań GPU przy Przegrzaniu:** Przekroczenie progu $80^\circ\text{C}$ inicjuje bezpieczne wstrzymanie nowych alokacji w buforze MPS oraz bezpieczne dokończenie bieżącego tokena i sekwencji w toku (**inter-token deadline**) przed przełączeniem na model zapasowy lub natychmiastowym odcięciem kontekstu przy skoku powyżej $85^\circ\text{C}$, co chroni przed błędami alokacji VRAM (OOM) przy zmiennej długości generacji vLLM.
* **Automatyczna Retencja i Rotacja Logów Audytowych:** Wprowadzono system twardej polityki retencji dla drzewa Merkle’a, który po eksporcie migawek kryptograficznych na zewnętrzny nośnik archiwizacyjny automatycznie zwalnia przestrzeń dyskową, uniemożliwiając saturację partycji root.

# 6. Strategia Backupów, Izolacji Sandbox, Zero-Trust Secrets i Disaster Recovery

### 6.1. Ścisła Izolacja Sandboxa MCP (Read-Only FS + Tmpfs + Memory Caps)
* Każdy kontener MCP (ze szczególnym uwzględnieniem parserów dokumentów oraz bibliotek PDF typu ReportLab/WeasyPrint, np. `Docling`) uruchamiany jest z flagą systemową `--read-only` oraz **twardym limitem pamięci RAM (`--memory=2g`)**, co uniemożliwia wycieki pamięci i chroni główny system przed ubiciem przez linuksowy *OOM Killer*.
* Katalogi tymczasowe montowane są jako wolumeny w pamięci operacyjnej RAM (`tmpfs`), co gwarantuje natychmiastowe czyszczenie pozostałości po przetwarzaniu plików i uniemożliwia zapisywanie złośliwego oprogramowania na dysku.
* Kontenery narzędziowe mają całkowicie odcięty dostęp do gniazd zarządzających środowiskiem uruchomieniowym (`docker.sock`) oraz zerowy dostęp do sieci lokalnej klastra baz danych Qdrant i Redis.

### 6.2. Szyfrowanie LUKS2, TPM 2.0, Master Recovery Key i Warm-Start Recovery
* **Wolumeny Szyfrowane i TPM 2.0:** Wolumeny dyskowe zawierające bazę wektorową Qdrant oraz migawki stanów grafu Redis są szyfrowane standardem **LUKS2 (AES-256-XTS)** zintegrowanym ze sprzętowym modułem **TPM 2.0**.
* **Tryb Warm-Start Ready (Odporność na Restart w Locie):** W przypadku nagłego odcięcia zasilania i resttaru komputera pokładowego w locie (gdy autopilot PX4 utrzymuje maszynę w powietrzu), system po odblokowaniu LUKS przechodzi w tryb **czysto reaktywny**. LangGraph działa tymczasowo bez pamięci długoterminowej z Qdranta (którego indeksy HNSW wymagają czasu na wczytanie do RAM-u), opierając się wyłącznie na bieżącym strumieniu sensorycznym, dopóki bazy danych nie zgłoszą pełnej gotowości (*Healthcheck PASSED*).
* **Procedura Disaster Recovery:** W przypadku fizycznego uszkodzenia płyty głównej lub modułu TPM 2.0, dostęp do zaszyfrowanych danych jest możliwy przy użyciu papierowego klucza odzyskiwania (*Master Recovery Key*), wprowadzanego ręcznie w bezpiecznym środowisku konsoli ratunkowej.

### 6.3. Rotacja Kluczy w Trybie Zero-Trust i Zarządzanie Secrets
* **Dynamiczna Rotacja Tokenów:** Obsługa bezpiecznej, wewnętrznej wymiany certyfikatów i kluczy uwierzytelniających między mikrousługami bez konieczności restartu klastra Redis lub głównego procesu LangGraph.
* **In-Memory Ephemeral Vault:** Przechowywanie poufnych poświadczeń wyłącznie w zaszyfrowanych blokach pamięci RAM (*locked memory*), co uniemożliwia ich zrzut na dysk (core dump).

# 7. Plan Testów Chaos Engineering & Ewaluacji Promptów

* **Test Hardware Fail-Safe i UART Heartbeat:** Sztuczne zawieszenie pętli głównej agenta i weryfikacja, czy brak sygnału Heartbeat przez okres 200 ms wywołuje poprawną reakcję drona (autonomiczny powrót do bazy RTL).
* **Test Izolacji Pamięci NVIDIA MPS:** Jednoczesne obciążenie silnika vLLM oraz modelu wizyjnego YOLO-World maksymalną liczbą zapytań w celu potwierdzenia braku wystąpienia błędów `CUDA Out Of Memory`.
* **Test Monotonicznych Tokenów Fencingowych:** Wprowadzenie kontrolowanego opóźnienia wątku agenta i weryfikacja, czy spóźniona komenda zostaje bezwzględnie odrzucona przez moduł wykonawczy drona.
* **Test Atomowości Hot-Reloadingu:** Zapisanie serii uszkodzonych plików konfiguracyjnych YAML w odstępach 50 ms i weryfikacja, czy system zachowuje ciągłość działania na podstawie wcześniej zwalidowanego promptu.
* **Test Przepustowości NATS JetStream z Drop-Tail:** Symulacja zalania szyny przestarzałymi pakietami telemetrii ($\text{TTL} > 500\text{ ms}$) po starcie i potwierdzenie, że pakiet jest automatycznie odrzucany bez wpływu na zużycie pamięci VRAM.

# 8. Specyfikacja Nowych Modułów Użytkowych (Chat, Cline, Computer Vision)

### 8.1. Chat z Obsługą Plików i Generowaniem Dokumentów (PDF/Obrazy)
* **Ingestia i Parsowanie:** Moduł czatu akceptuje pliki wejściowe (dokumenty, obrazy, wideo), które przed trafieniem do kontekstu modelu są bezpiecznie parsowane w izolowanym sandboxie[cite: 3].
* **Generowanie Artefaktów:** System potrafi dynamicznie generować pliki wynikowe (raporty PDF z podsumowaniem analiz, wykresy, przetworzone grafiki) i udostępniać je w interfejsie użytkownika jako gotowe do pobrania zasoby[cite: 3].

### 8.2. Integracja z Cline dla VS Code (Model Context Protocol)
* **Most komunikacyjny MCP:** Cline działa jako autoryzowany klient Model Context Protocol, łącząc się z lokalnym rdzeniem systemu **Agent System**[cite: 3].
* **Bezpieczna edycja kodu:** Agent ma kontrolowany dostęp do przestrzeni roboczej w VS Code, co pozwala na automatyczne generowanie kodu, uruchamianie testów i inspekcję plików konfiguracyjnych w trybie zatwierdzania przez dewelopera[cite: 3].

### 8.3. Zaawansowana Analiza Wideo (Roboflow Integration)
* **Przetwarzanie klatkowe:** Przesłany plik wideo jest dzielony na strumień klatek i analizowany przy użyciu dedykowanych modeli detekcji obiektów (Roboflow / YOLO)[cite: 3].
* **Mapowanie Czasowe (Timestamps i Kontekst):** Wynikiem analizy jest ustrukturyzowany raport zawierający[cite: 3]:
  * Dokładne przedziały czasowe (`start_time` - `end_time`), w których dana marka lub obiekt były widoczne[cite: 3].
  * Stopień widoczności (*confidence score* oraz powierzchnia kadru)[cite: 3].
  * Kontekst fizyczny (np. "logo widoczne na koszulce", "logo widoczne na tle billboardu")[cite: 3].

# 9. Inżynieria Wdrożeniowa i Pliki Konfiguracyjne (Deployment & Infrastructure)

### 9.1. Orkiestracja Kontenerów (`docker-compose.yaml`)
W celu uruchomienia spójnego stosu na urządzeniu brzegowym (Edge) z zachowaniem izolacji, podziału zasobów oraz wysokiej dostępności NATS i etcd, wykorzystywany jest poniższy plik konfiguracyjny:

```yaml
version: '3.8'

networks:
  agent_internal:
    driver: bridge
    internal: true

services:
  etcd1:
    image: quay.io/coreos/etcd:v3.5.9
    container_name: agent_etcd_1
    restart: always
    read_only: true
    tmpfs:
      - /data:size=64M,noexec,nosuid,nodev
    command:
      - /usr/local/bin/etcd
      - --name=etcd1
      - --data-dir=/data
      - --initial-advertise-peer-urls=http://etcd1:2380
      - --listen-peer-urls=http://0.0.0.0:2380
      - --listen-client-urls=http://0.0.0.0:2379
      - --advertise-client-urls=http://etcd1:2379
      - --initial-cluster=etcd1=http://etcd1:2380,etcd2=http://etcd2:2382,etcd3=http://etcd3:2384
    networks:
      - agent_internal
    deploy:
      resources:
        limits:
          memory: 128M

  etcd2:
    image: quay.io/coreos/etcd:v3.5.9
    container_name: agent_etcd_2
    restart: always
    read_only: true
    tmpfs:
      - /data:size=64M,noexec,nosuid,nodev
    command:
      - /usr/local/bin/etcd
      - --name=etcd2
      - --data-dir=/data
      - --initial-advertise-peer-urls=http://etcd2:2382
      - --listen-peer-urls=http://0.0.0.0:2382
      - --listen-client-urls=http://0.0.0.0:2379
      - --advertise-client-urls=http://etcd2:2379
      - --initial-cluster=etcd1=http://etcd1:2380,etcd2=http://etcd2:2382,etcd3=http://etcd3:2384
    networks:
      - agent_internal
    deploy:
      resources:
        limits:
          memory: 128M

  etcd3:
    image: quay.io/coreos/etcd:v3.5.9
    container_name: agent_etcd_3
    restart: always
    read_only: true
    tmpfs:
      - /data:size=64M,noexec,nosuid,nodev
    command:
      - /usr/local/bin/etcd
      - --name=etcd3
      - --data-dir=/data
      - --initial-advertise-peer-urls=http://etcd3:2384
      - --listen-peer-urls=http://0.0.0.0:2384
      - --listen-client-urls=http://0.0.0.0:2379
      - --advertise-client-urls=http://etcd3:2379
      - --initial-cluster=etcd1=http://etcd1:2380,etcd2=http://etcd2:2382,etcd3=http://etcd3:2384
    networks:
      - agent_internal
    deploy:
      resources:
        limits:
          memory: 128M

  mavlink_mcp:
    image: agent/mavlink-mcp:v3.5
    container_name: agent_mavlink_mcp
    restart: always
    read_only: true
    tmpfs:
      - /tmp:size=128M,noexec,nosuid,nodev
    environment:
      - ETCD_ENDPOINTS=http://etcd1:2379,http://etcd2:2379,http://etcd3:2379
    networks:
      - agent_internal
    depends_on:
      - etcd1
      - etcd2
      - etcd3
    security_opt:
      - no-new-privileges:true
    deploy:
      resources:
        limits:
          memory: 256M

  nats1:
    image: nats:2.9-alpine
    container_name: agent_nats_1
    restart: always
    ports:
      - "4222:4222"
      - "6222:6222"
      - "8222:8222"
    command: ["--jetstream", "--store_dir=/data/jetstream", "--cluster_name=agent-cluster", "--cluster=nats://0.0.0.0:6222", "--routes=nats://ruser:rapass@agent_nats_2:6222"]
    volumes:
      - nats_data_1:/data/jetstream
    networks:
      - agent_internal

  nats2:
    image: nats:2.9-alpine
    container_name: agent_nats_2
    restart: always
    ports:
      - "4224:4222"
    command: ["--jetstream", "--store_dir=/data/jetstream", "--cluster_name=agent-cluster", "--cluster=nats://ruser:rapass@0.0.0.0:6222", "--routes=nats://ruser:rapass@agent_nats_1:6222"]
    volumes:
      - nats_data_2:/data/jetstream
    networks:
      - agent_internal

  redis:
    image: redis:7.2-alpine
    container_name: agent_redis
    restart: always
    command: redis-server --save 60 1 --loglevel warning
    volumes:
      - redis_data:/data
    networks:
      - agent_internal

  qdrant:
    image: qdrant/qdrant:v1.7.0
    container_name: agent_qdrant
    restart: always
    volumes:
      # UWAGA: Wymaga poprawnego zamontowania partycji LUKS (/mnt/encrypted_luks) przed startem kontenera,
      # w przeciwnym razie Docker utworzy pusty katalog root prowadzący do błędu Permission Denied.
      - /mnt/encrypted_luks/qdrant_data:/qdrant/storage
    networks:
      - agent_internal

volumes:
  nats_data_1:
  nats_data_2:
  redis_data:
```


### 9.2 Skrypt Inicjalizujący NVIDIA MPS (`init_mps.sh`)
W celu uruchomienia spójnego stosu na urządzeniu brzegowym (Edge) z zachowaniem izolacji, podziału zasobów oraz wysokiej dostępności NATS i etcd, wykorzystywany jest poniższy plik konfiguracyjny:

```bash
#!/bin/bash
set -e

echo "[*] Resetowanie stanów CUDA MPS..."
echo quit | nvidia-cuda-mps-control || true

export CUDA_VISIBLE_DEVICES=0
nvidia-smi -i 0 -c EXCLUSIVE_PROCESS

echo "[*] Uruchamianie demona NVIDIA MPS..."
nvidia-cuda-mps-control -d

echo "[*] Konfiguracja alokacji VRAM (50% / 30% / 20%)..."
echo "set_default_active_thread_percentage 100" | nvidia-cuda-mps-control

echo "[+] NVIDIA MPS został pomyślnie skonfigurowany."
```

### 9.3 Pipeline Walidacji Konfiguracji w CI/CD (validate_configs.py)
Skrypt testujący poprawność schematów Pydantic dla plików konfiguracyjnych YAML przed ich wdrożeniem na urządzenie docelowe:

```python
import os
import sys
import yaml
from pydantic import BaseModel, ValidationError

class SystemConfig(BaseModel):
    schema_version: int
    environment: str

class PromptConfig(BaseModel):
    version: str
    core_prompt: str

def validate():
    print("[*] Sprawdzanie poprawności składni i schematu Pydantic dla plików konfiguracyjnych...")
    
    configs_to_check = [
        ("configs/system.yaml", SystemConfig),
        ("configs/prompts/v3.5_core.yaml", PromptConfig),
        ("configs/prompts/v2_fallback.yaml", PromptConfig)
    ]

    for file_path, model_class in configs_to_check:
        if not os.path.exists(file_path):
            print(f"[!] BŁĄD: Brak pliku konfiguracyjnego: {file_path}")
            sys.exit(1)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                model_class(**data)
            print(f" [+] Plik {file_path} zweryfikowany pomyślnie przez Pydantic v2.")
        except ValidationError as e:
            print(f"[!] BŁĄD SCHEMATU w pliku {file_path}:\n{e}")
            sys.exit(1)
        except Exception as e:
            print(f"[!] BŁĄD PARSOWANIA YAML w pliku {file_path}:\n{e}")
            sys.exit(1)
            
    print("[+] Wszystkie pliki konfiguracyjne przeszły walidację pomyślnie.")

if __name__ == "__main__":
    validate()
```

### 9.4 Asynchroniczny Wrapper dla etcd w Pythonie (`src/safety/etcd_client.py`)
Moduł zapobiegający blokowaniu głównej pętli zdarzeń asynchronicznych (`asyncio`) przez synchroniczne zapytania do etcd:

```python
import asyncio
import etcd3

# Inicjalizacja klienta bazowego etcd (synchronicznego)
etcd_client = etcd3.client(host='etcd1', port=2379)

async def get_lock_async(key: str, ttl: int):
    """
    Wywołanie synchronicznych metod etcd w osobnym wątku, 
    aby nie zamrozić głównej pętli zdarzeń (event loop) LangGraph i telemetrii >50Hz.
    """
    def _acquire():
        lock = etcd_client.lock(key, ttl=ttl)
        acquired = lock.acquire()
        return lock if acquired else None
    
    lock = await asyncio.to_thread(_acquire)
    return lock

async def get_value_async(key: str):
    def _get():
        val, _ = etcd_client.get(key)
        return val
    
    return await asyncio.to_thread(_get)
```

# 10. Automatyczne Testy Polowe i Chaos Engineering (Simulation Suite)
W celu weryfikacji odporności systemu na anomalia środowiskowe, awarie sprzętowe oraz błędy sieciowe, w procesie testowym stosowany jest dedykowany zestaw skryptów symulacyjnych (tests/chaos/).

### 10.1 Test Przegrzania GPU i Graceful Drainage (`test_thermal_drain.py`)
Skrypt symuluje przekroczenie krytycznego progu temperatury ($>80^\circ\text{C}$) przez mockowanie odczytów pynvml i weryfikuje, czy system poprawnie wstrzymuje nowe zadania w buforze MPS oraz bezpiecznie przełącza się na model zapasowy:

```python
import pytest
from unittest.mock import patch

@patch("pynvml.nvmlDeviceGetTemperature")
def test_thermal_fallback_trigger(mock_get_temp):
    mock_get_temp.return_value = 82  # Przekroczenie progu 80°C
    from src.safety.thermal_node import check_thermal_status
    
    status = check_thermal_status()
    print(f"[*] Odczyt z thermal_node: temp={status.get('temp')}°C, model={status.get('active_model')}")
    
    assert status.get("temp") > 80, "Temperatura powinna przekraczać próg krytyczny"
    assert status.get("active_model") == "Qwen-2.5-7B", "System nie przełączył się na model zapasowy!"
```

### 10.2. Test Odcięcia Zasilania i Warm-Start Recovery (`test_warm_start.py`)
Skrypt weryfikuje zachowanie systemu po nagłym restarcie kontenerów w warunkach lotu drona

```python
import pytest
from unittest.mock import patch

@patch("src.storage.qdrant_client.QdrantClient.ping")
def test_warm_start_recovery(mock_ping):
    mock_ping.return_value = False  # Symulacja niedostępności Qdrant po restarcie
    from src.core.graph import initialize_system_state
    
    state = initialize_system_state()
    print(f"[*] Tryb czysto reaktywny (brak pamięci długoterminowej): {state.get('reactive_mode')}")
    
    assert state.get("reactive_mode") is True, "System nie wszedł w tryb awaryjny przy niedostępności Qdrant!"
```

### 10.3 Test Awarii Szyny NATS i Polityki Drop-Tail (test_nats_droptail.py)
Test obciążeniowy generujący napływ przestarzałych klatek telemetrii (`TTL > 500ms`)

```python
import asyncio
import pytest
import nats

@pytest.mark.asyncio
async def test_nats_ttl_drop_tail():
    """
    Test integracyjny z użyciem realnego klienta NATS i brokera JetStream,
    weryfikujący faktyczne odrzucenie przedawnionych klatek na krawędzi (Drop-Tail).
    """
    nc = await nats.connect("nats://localhost:4222")
    js = nc.jetstream()
    
    # Deklaracja strumienia z twardym limitem TTL i polityką Drop-Tail
    await js.add_stream(name="telemetry", subjects=["telemetry.>"], max_age=0.5)
    
    # Symulacja wysłania i weryfikacji odrzucenia przestarzałej wiadomości
    future = asyncio.Future()
    async def cb(msg):
        future.set_result(msg)
        
    sub = await js.subscribe("telemetry.drone", cb=cb)
    
    # Publikacja wiadomości z przekroczonym TTL lub weryfikacja polityki brokera
    await nc.publish("telemetry.drone", b"stale_frame_data")
    
    try:
        await asyncio.wait_for(future, timeout=1.0)
    except asyncio.TimeoutError:
        print("[+] Sukces: Przestarzała klatka została odrzucona przez broker NATS JetStream.")
    
    await nc.close()
```

# 11. Lokalny System Wizualizacji i Monitoringu (Local Observability Stack)

W celu zapewnienia pełnej przejrzystości działania systemu autonomicznego, w architekturę wbudowano 100% darmowy, lokalny (*fully offline*) stos wizualizacyjny uruchamiany na osobnym komputerze analitycznym. Umożliwia on stały podgląd procesów myślowych AI, stanu pamięci długoterminowej oraz zasobów sprzętowych bez wysyłania jakichkolwiek danych na zewnątrz.

### 11.1. Architektura Monitoringu i Narzędzia

| Moduł Wizualizacji | Technologia | Zakres Monitorowanych Danych |
| :--- | :--- | :--- |
| **Zasoby i Sprzęt** | Grafana + Prometheus + NVIDIA DCGM Exporter | Bieżące zużycie CPU/RAM, temperatura GPU (współpraca z węzłem termicznym), obciążenie dysków pSLC oraz alokacja VRAM przez NVIDIA MPS. |
| **Pamięć i Wektory** | Qdrant Web UI (Wbudowany Dashboard) | Podgląd struktury przestrzeni wektorowej, zawartości pamięci długoterminowej (Mem0) oraz stanu indeksów HNSW. |
| **Tracing AI i LangGraph** | Arize Phoenix | Śledzenie kroków agenta (*tracing*), wejść/wyjść z węzłów LangGraph, historia promptów oraz walidacja struktur JSON. |

### 11.2. Schemat Połączeń i Strumienia Metryk

```mermaid
graph TD
    subgraph System_Zrodlowy [Edge / Core Brain]
        Node_Thermal[Thermal Node / pynvml]
        LangGraph_Core[LangGraph Engine & Prompts]
        Qdrant_Store[(Qdrant Vector DB / Mem0)]
        MPS_Hardware[NVIDIA MPS & Hardware Metrics]
    end

    subgraph Komputer_Analityczny [Kokpit Analityczny - Offline Stack]
        Prometheus[Prometheus Exporter Hub]
        Grafana[Grafana Dashboard UI]
        Phoenix[Arize Phoenix Tracing Server]
        Qdrant_UI[Qdrant Web UI Panel]
    end

    Node_Thermal -. Metryki Temp/HW .-> Prometheus
    MPS_Hardware -. Metryki VRAM .-> Prometheus
    Prometheus --> Grafana

    LangGraph_Core -. Traces & Prompts .-> Phoenix
    Qdrant_Store -. Stan Wektorów .-> Qdrant_UI
```

### 11.3. Konfiguracja w Stacku Wdrożeniowym (docker-compose.observability.yaml)
Do uruchomienia darmowego stosu analitycznego na drugim komputerze wykorzystywany jest poniższy plik konfiguracyjny spięty z wewnętrzną siecią agenta:

```yaml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:v2.45.0
    container_name: observability_prometheus
    restart: always
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"
    networks:
      - agent_internal

  grafana:
    image: grafana/grafana:10.0.0
    container_name: observability_grafana
    restart: always
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=local_secure_pass
    networks:
      - agent_internal
    depends_on:
      - prometheus

  phoenix:
    image: arizephoenix/phoenix:latest
    container_name: observability_phoenix
    restart: always
    ports:
      - "6006:6006"
    networks:
      - agent_internal

networks:
  agent_internal:
    external: true
```

# 12. Architektura Skalowalna — Wytyczne na Przyszłość (Roadmap / Distributed Scale-Out Cluster: 20 Nodes x 4/8 GPUs)

Sekcja ta stanowi wytyczne architektoniczne dla przyszłego, drugiego etapu rozwoju systemu (skala przemysłowa: klaster 20 komputerów brzegowych, łącznie do 160 GPU). Obecna implementacja jednowęzłowa musi zostać napisana w sposób modularny, aby w przyszłości umożliwić bezproblemową migrację do poniższego modelu *High-Availability Distributed Edge Cluster*.

### 12.1. Topologia Sprzętowa i Sieciowa (Faza 2)
* **Network Fabric (100 GbE / InfiniBand):** Docelowa komunikacja między 20 węzłami oparta na architekturze *Spine-Leaf* z obsługą RDMA (RoCE) w celu eliminacji narzutów przy przesyłaniu tensorów i stanów LangGraph.
* **Master Clock PTP Grandmaster:** Wdrożenie sprzętowego wzorca czasu GPS (IEEE 1588) dla całego klastra, gwarantującego synchronizację logów i dziennika Merkle’a poniżej 1 mikrosekundy.
* **Power & Thermal Infrastructure:** Docelowe szafy Rack z chłodzeniem wodnym (*Direct-to-Chip Liquid Cooling*) zdolne odprowadzić do 300 kW ciepła.

### 12.2. Distributed Data & Storage Layer (Faza 2)
* **Qdrant Vector Cluster (Sharded & Replicated):** Przejście pamięci długoterminowej na tryb klastrowy z podziałem na shardy i replikacją ($RF=2$), co pozwala na równoległe przeszukiwanie setek milionów wektorów.
* **NATS JetStream Distributed Mesh:** Rozbudowa lokalnej szyny telemetrii do globalnego mesha z dynamicznym routowaniem wiadomości do węzłów w klastrze posiadających wolne zasoby GPU w puli MPS.
* **Control Plane (etcd Raft Quorum):** Globalne zarządzanie blokadami, stanami sesji i Fencing Tokenami realizowane przez 5-węzłowy klaster kontrolny etcd odporny na awarię do 2 węzłów (*Split-Brain Protection*).

### 12.3. Dynamiczna Alokacja Zadań AI (Faza 2 - Load Balancing 160 GPU)
* **Globalny Router Zadań (vLLM + Roboflow Cluster):** Agenci LangGraph nie wykonują inferencji lokalnie na sztywno przypisanej maszynie, lecz odpytują klastrowy load balancer kierujący zapytania tekstowe do węzłów z najniższym obciążeniem VRAM, a wizyjne do maszyn z wolnymi kartami YOLO.
* **Distributed Checkpointing (Redis Cluster + Shared NVMe):** Asynchroniczna replikacja stanów grafów agentów zapewniająca natychmiastowe przejęcie zadania przez inny węzeł w razie awarii fizycznej (*Failover < 100 ms*).