import httpx
from typing import Dict, Any, Optional, List
from app.core.config import settings
from langchain_ollama import OllamaLLM, OllamaEmbeddings

class LLMFactory:
    """
    Zunifikowana fabryka modeli AI. Asynchronicznie konfiguruje i zarządza
    instancjami modeli przypisanych do konkretnych ról z pliku models.yaml.
    Gwarantuje poprawne bindowanie zaawansowanych parametrów pod Ollamę.
    """
    _instances: Dict[str, Any] = {}

    @classmethod
    async def ensure_models_setup(cls) -> None:
        """
        [Self-Healing] Automatycznie sprawdza bibliotekę Ollamy i pobiera 
        wszystkie brakujące modele zdefiniowane w pliku models.yaml.
        """
        base_url = settings.ollama_global_settings.base_url
        print(f"[Ollama Sync] Łączę się z Ollamą pod adresem: {base_url}...")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                # 1. Pobieramy listę aktualnie zainstalowanych modeli w Ollamie
                response = await client.get(f"{base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
                installed_models = [m["name"] for m in data.get("models", [])]
            except Exception as e:
                print(f"❌ [Ollama Sync] Nie można nawiązać połączenia z Ollamą! Sprawdź czy kontener działa. Błąd: {e}")
                return

            # 2. Wyciągamy unikalne nazwy modeli z naszej konfiguracji models.yaml
            target_models = set()
            for role_key, config in settings.models.items():
                if config.name:
                    target_models.add(config.name)
            if settings.default_role in settings.models:
                target_models.add(settings.models[settings.default_role].name)

            # 3. Pętla weryfikacji i automatycznego pobierania (pull)
            for model_name in target_models:
                # Sprawdzamy czy model jest już na dysku (obsługujemy też wersje z tagiem lub bez)
                if model_name in installed_models or f"{model_name}:latest" in installed_models:
                    print(f"✅ [Ollama Sync] Model '{model_name}' jest już zainstalowany.")
                    continue
                
                print(f"📥 [Ollama Sync] Wykryto brak modelu! Rozpoczynam pobieranie: {model_name}...")
                print("   (To może zająć kilka minut w zależności od Twojego łącza...)")
                
                # Zwiększamy timeout do zera (brak limitu) dla pobierania gigabajtowych plików modeli
                async with httpx.AsyncClient(timeout=None) as pull_client:
                    try:
                        # Strumieniujemy żądanie pull do Ollamy
                        async with pull_client.stream("POST", f"{base_url}/api/pull", json={"name": model_name}) as stream:
                            async for chunk in stream.aiter_text():
                                # Możesz odkomentować poniższą linię, jeśli chcesz widzieć surowy postęp pobierania bajtów w logach:
                                # print(chunk, end="", flush=True)
                                pass
                        print(f"🎉 [Ollama Sync] Pomyślnie pobrano i zindeksowano model: {model_name}")
                    except Exception as pull_err:
                        print(f"❌ [Ollama Sync] Błąd podczas pobierania modelu {model_name}: {pull_err}")

    @classmethod
    def get_model_by_role(cls, role_key: str) -> OllamaLLM:
        """
        Zwraca lub tworzy instancję modelu LLM dla danej roli (Flyweight Pattern).
        Poprawnie mapuje parametry num_ctx, temperature itp. do wewnętrznego słownika Ollamy.
        """
        if role_key not in settings.models:
            print(f"[Factory] Brak roli '{role_key}' w models.yaml. Używam domyślnego modelu.")
            # Mapujemy domyślną rolę podaną w konfiguracji
            role_key = settings.default_role

        model_config = settings.models[role_key]
        instance_key = f"llm_{role_key}_{model_config.name}"

        if instance_key not in cls._instances:
            print(f"[Factory] Inicjalizuję model '{model_config.name}' dla roli '{role_key}'...")
            
            # POPRAWKA: Zamiast Ollama() używamy OllamaLLM() z nowej paczki
            cls._instances[instance_key] = OllamaLLM(
                base_url=settings.ollama_global_settings.base_url,
                model=model_config.name,
                timeout=settings.ollama_global_settings.timeout,
                keep_alive=settings.ollama_global_settings.keep_alive,
                num_ctx=model_config.num_ctx,
                temperature=model_config.temperature,
                top_p=model_config.top_p,
                num_predict=model_config.num_predict,
                num_thread=settings.ollama_global_settings.num_threads
            )
            
        return cls._instances[instance_key]

    @classmethod
    def get_embedding_engine(cls) -> OllamaEmbeddings:
        """Zwraca dedykowany, zoptymalizowany silnik embeddingów dla bazy PGVector."""
        instance_key = "embeddings_global"
        
        if instance_key not in cls._instances:
            embed_config = settings.models.get("embedding")
            if not embed_config:
                raise ValueError("Krytyczny błąd: Brak konfiguracji roli 'embedding' w pliku models.yaml!")
                
            print(f"[Factory] Inicjalizuję silnik embeddingów: {embed_config.name}")
            cls._instances[instance_key] = OllamaEmbeddings(
                base_url=settings.ollama_global_settings.base_url,
                model=embed_config.name,
                # Ograniczamy kontekst bazy zgodnie z plikiem models.yaml
                num_ctx=embed_config.num_ctx
            )
            
        return cls._instances[instance_key]

    @classmethod
    async def unload_all_models(cls) -> bool:
        """
        Wymusza na lokalnej Ollamie natychmiastowe wyczyszczenie VRAM-u Twojej karty graficznej.
        Niezbędne przy płynnej żonglerce modelami (np. przejście z kodu na wideo/wizję).
        """
        print("[Factory] Żądanie natychmiastowego zwolnienia pamięci VRAM GPU...")
        async with httpx.AsyncClient() as client:
            try:
                # API Ollamy zwalnia pamięć, gdy wyślemy pusty model z parametrem keep_alive = 0
                response = await client.post(
                    f"{settings.ollama_global_settings.base_url}/api/generate",
                    json={"model": "", "keep_alive": 0},
                    timeout=5.0
                )
                return response.status_code == 200
            except Exception as e:
                print(f"[Factory Error] Nie udało się wyczyścić pamięci GPU: {e}")
                return False
