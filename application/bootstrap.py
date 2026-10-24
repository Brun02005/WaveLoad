"""
application/bootstrap.py
========================
Composition Root for WaveLoad.
Responsible for instantiating core infrastructure, repositories, and services
and wiring them together. Ensures singletons remain singletons.
"""

from storage.sqlite_track_repository import SqliteTrackRepository
from storage.collection_repository import SqliteCollectionRepository
from storage.tag_repository import SqliteTagRepository
from services.collection_service import CollectionService
from services.auto_tagging_service import AutoTaggingService
from services.tagging_service import TaggingService
from services.track_service import TrackService
from services.library_service import LibraryService
from services.settings_service import SettingsService
from services.audio_player_service import AudioPlayerService
from application.import_use_case import ImportUseCase
from application.analysis_coordinator import AnalysisCoordinator

class ApplicationContainer:
    """
    Dependency Injection Container.
    Holds single instances of repositories and services for the application's lifetime.
    """
    def __init__(self):
        # 1. Repositories
        self.track_repository = SqliteTrackRepository()
        self.tag_repository = SqliteTagRepository()
        self.collection_repository = SqliteCollectionRepository()

        # 2. Services / Use Cases
        self.settings_service = SettingsService()
        self.track_service = TrackService(repository=self.track_repository)
        self.library_service = LibraryService(repository=self.track_repository)
        self.import_use_case = ImportUseCase(repository=self.track_repository)
        self.analysis_coordinator = AnalysisCoordinator(repository=self.track_repository)
        self.audio_player_service = AudioPlayerService()

        # 3. Etiquetado automático. Se suscribe al event bus en su constructor:
        # hay que conservar la referencia o el suscriptor muere con el objeto.
        self.tagging_service = TaggingService(self.tag_repository)
        self.auto_tagging_service = AutoTaggingService(self.tagging_service)

        # 4. Motor de Collections
        self.collection_service = CollectionService(
            collection_repository=self.collection_repository,
            track_repository=self.track_repository,
            tag_repository=self.tag_repository,
        )

# Global Application Container
app_container = ApplicationContainer()
