# BackEnd/app/models/__init__.py
from ..database import Base
from .auth import UserModel, RoleModel, PermissionModel, RolePermissionModel
from .scada import (
    TagModel, AlarmModel, TagHistoryModel,
    HistoricoExtrusoraS1Model, HistoricoExtrusoraS2Model, HistoricoExtrusoraMeltblownModel,
    HistoricoProcesoMecanicoModel, HistoricoMotoresVelocidadesModel, HistoricoDosificacionGlobalModel,
    OEELogModel
)