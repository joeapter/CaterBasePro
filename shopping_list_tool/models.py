from client_estimates.models import ShoppingList


class ShoppingListBulkImport(ShoppingList):
    class Meta:
        proxy = True
        app_label = "shopping_list_tool"
        verbose_name = "Shopping List"
        verbose_name_plural = "Shopping List"
