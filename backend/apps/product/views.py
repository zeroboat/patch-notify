from django.shortcuts import render
from django.views.generic import TemplateView
from web_project import TemplateLayout
from .models import Product


# Create your views here.

class ProductManagementView(TemplateView):
    template_name="product/product_management.html"
    # Predefined function
    def get_context_data(self, **kwargs):
        # A function to init the global layout. It is defined in web_project/__init__.py file
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        products = Product.objects.all().order_by('solution__name')
        context.update(
            {
                'products': products,
            }
        )

        return context
