
#!/bin/bash
# =============================================================================
# sync-models.sh - Pobiera wszystkie modele z config/models.yaml
# =============================================================================

set -e  # Zatrzymaj na błędzie

echo "🚀 Synchronizacja modeli Ollama..."
echo "======================================="
echo ""

# Szukamy pliku config/models.yaml (lub models.yaml w aktualnym katalogu)
MODELS_FILE="${1:-config/models.yaml}"

if [ ! -f "$MODELS_FILE" ]; then
  echo "❌ Plik $MODELS_FILE nie znaleziony!"
  echo "Dostępne pliki:"
  ls -la *.yaml config/*.yaml 2>/dev/null || true
  exit 1
fi

# Pobierz listę modeli do pobrania z models.yaml
while IFS= read -r line; do
  # Szukamy linii "name: model_name"
  if [[ $line =~ name:(.+)$ ]]; then
    model_name="${BASH_REMATCH[1]}"
    # Odejmuje cudzysłow i spacje
    model_name=$(echo "$model_name" | sed 's/"//g' | xargs)
    
    echo "Pobieram: $model_name..."
    echo "----------------------------------------"
    
    # Pobierz obraz z modelem - to pobierze layer do hosta Docker
    docker pull "ollama/ollama:$model_name" || {
      echo "  ⚠️  Błąd przy pobrańiu layer: $model_name"
      continue  # Kontynuuj z innym modelem
    }
    
    echo "✅ Layer modelu pobrany!"
    echo ""
  fi
done < "$MODELS_FILE"

echo "======================================"
echo "🎉 Gotowe! Modele są pobrane jako Docker images."
echo ""
echo "Używanie modeli w kontenerze MemoryCore AI:"
echo "----------------------------------------"
echo "docker exec ai-memory ollama run llama3.1:8b-instruct 'Witam!'"
echo ""
echo "Albo po uruchomieniu Ollama na hostzie:"
echo "----------------------------------------"
echo "ollama serve &  # Uruchamiamy serwer Ollama w tle"
echo "ollama list     # Lista pobranych modeli"
echo "ollama run llama3.1:8b-instruct 'Witam!'"
