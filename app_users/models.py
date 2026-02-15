from client_estimates.models import CatererUserAccess


class AppUser(CatererUserAccess):
    class Meta:
        proxy = True
        verbose_name = "App User"
        verbose_name_plural = "App Users"
