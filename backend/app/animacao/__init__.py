"""Animação de cena (briefing, seção 3.2): personagens recortados, cenário e câmera animados por código, sem IA de vídeo.

É o modo rápido e consistente para vídeos longos: os personagens da biblioteca (PNG transparente) são compostos sobre o
cenário e se movem com squash and stretch, saltos, balanço, entradas e câmera lenta; a fala faz o personagem "pulsar" no
ritmo do áudio. Cada quadro é desenhado com o Pillow e enviado ao ffmpeg, que codifica o clipe.
"""
