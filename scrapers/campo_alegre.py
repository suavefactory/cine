"""
Scraper: Teatro Campo Alegre (Porto)
Fonte: https://medeiafilmes.com/filmes-em-exibicao — mesmo sistema que o Nimas
"""

from nimas import scrape_medeia_cinema

CINEMA_ID   = "campo_alegre"
CINEMA_SLUG = "teatro-campo-alegre"


def scrape():
    return scrape_medeia_cinema(CINEMA_ID, CINEMA_SLUG, "Campo Alegre")


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), ensure_ascii=False, indent=2))
