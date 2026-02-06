from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from web_project import TemplateLayout
from .models import PatchNote
from apps.product.models import Product

# Create your views here.
class PatchNoteDetailView(TemplateView):
    template_name = "patchnote/patch_list.html"

    def get_context_data(self, **kwargs):
        # 1. 부모 클래스의 컨텍스트 가져오기
        context = super().get_context_data(**kwargs)
        
        # 2. Sneat 레이아웃 초기화 (여기서 layout_path 등이 설정됨)
        context = TemplateLayout.init(self, context)

        # 3. URL에서 넘어온 product_id로 데이터 조회
        product_id = self.kwargs.get('product_id')
        product = get_object_or_404(Product, id=product_id)
        
        # 4. 패치노트 데이터 조회 (성능 최적화 포함)
        patch_notes = PatchNote.objects.filter(product=product).prefetch_related(
            'features__children',
            'improvements__children',
            'bugfixes__children',
            'remarks__children'
        ).order_by('-release_date', '-version')

        # 5. 컨텍스트에 추가 데이터 주입
        context.update({
            'selected_product': product,
            'patch_notes': patch_notes,
        })

        return context

def patch_note_append(request):
    if request.method == "POST":
        try:
            print(request.POST)
            print("test")
        except Exception as e:
            print("Error is "+ str(e))
    else:
        print("")
