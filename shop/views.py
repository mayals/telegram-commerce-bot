from django.shortcuts import render, get_object_or_404
from .models import Category, Product
from django.core.paginator import Paginator

def category_list(request):
    categories = Category.objects.all()
    return render(request, 'category_list.html', {'categories': categories})


def product_list(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    products = Product.objects.filter(category=category)

    # PAGINATION → 5 per page
    paginator = Paginator(products, 2)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'product_list.html', {
        'category': category,
        'page_obj': page_obj,
    })


def product_detail(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    return render(request, 'product_detail.html', {'product': product})


