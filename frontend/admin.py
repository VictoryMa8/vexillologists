from django.contrib import admin
from .models import Country, FlagProgress, GameResult, Vexillologist

admin.site.register(Country)
admin.site.register(Vexillologist)
admin.site.register(FlagProgress)
admin.site.register(GameResult)
