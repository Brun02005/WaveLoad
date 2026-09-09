from PySide6.QtCore import QAbstractListModel, Qt, QModelIndex
from typing import List, Dict, Any

class PreviewModel(QAbstractListModel):
    # Custom Roles
    UrlRole = Qt.UserRole + 1
    MetadataRole = Qt.UserRole + 2
    IsDuplicateRole = Qt.UserRole + 3
    IsLoadingRole = Qt.UserRole + 4
    ErrorMsgRole = Qt.UserRole + 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self._urls: List[str] = []
        self._data: Dict[str, Dict[str, Any]] = {}

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._urls)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._urls)):
            return None

        url = self._urls[index.row()]
        item_data = self._data.get(url, {})

        if role == self.UrlRole:
            return url
        elif role == self.MetadataRole:
            return item_data.get("metadata", None)
        elif role == self.IsDuplicateRole:
            return item_data.get("is_duplicate", False)
        elif role == self.IsLoadingRole:
            return item_data.get("is_loading", True)
        elif role == self.ErrorMsgRole:
            return item_data.get("error_msg", None)
        return None

    def add_url(self, url: str):
        if url in self._urls:
            return
        
        row = len(self._urls)
        self.beginInsertRows(QModelIndex(), row, row)
        self._urls.append(url)
        self._data[url] = {
            "is_loading": True,
            "metadata": None,
            "is_duplicate": False,
            "error_msg": None
        }
        self.endInsertRows()

    def update_metadata(self, url: str, metadata: dict, is_duplicate: bool = False):
        if url not in self._urls:
            return
        
        self._data[url].update({
            "is_loading": False,
            "metadata": metadata,
            "is_duplicate": is_duplicate,
            "error_msg": None
        })
        
        row = self._urls.index(url)
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [self.MetadataRole, self.IsLoadingRole, self.IsDuplicateRole])

    def set_error(self, url: str, error_msg: str):
        if url not in self._urls:
            return
            
        self._data[url].update({
            "is_loading": False,
            "error_msg": error_msg,
            "metadata": None
        })
        
        row = self._urls.index(url)
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [self.ErrorMsgRole, self.IsLoadingRole])

    def remove_url(self, url: str):
        if url not in self._urls:
            return
            
        row = self._urls.index(url)
        self.beginRemoveRows(QModelIndex(), row, row)
        self._urls.pop(row)
        del self._data[url]
        self.endRemoveRows()

    def set_urls(self, urls: List[str]):
        """Sets the entire list of URLs to match the input box accurately."""
        # Find urls to add and remove
        current_urls = set(self._urls)
        target_urls = set(urls)
        
        urls_to_remove = current_urls - target_urls
        for url in urls_to_remove:
            self.remove_url(url)
            
        for url in urls:
            if url not in current_urls:
                self.add_url(url)
                
        # To strictly maintain order, we could rebuild the list completely
        # But for now, ensuring the sets match is usually enough. 
        # If strict order matching is required:
        if self._urls != urls:
            self.beginResetModel()
            old_data = self._data
            self._urls = list(urls)
            self._data = {}
            for u in self._urls:
                if u in old_data:
                    self._data[u] = old_data[u]
                else:
                    self._data[u] = {"is_loading": True, "metadata": None, "is_duplicate": False, "error_msg": None}
            self.endResetModel()

    def clear(self):
        self.beginResetModel()
        self._urls.clear()
        self._data.clear()
        self.endResetModel()

    def get_all_urls(self) -> List[str]:
        return list(self._urls)
