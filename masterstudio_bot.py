import os # Necesario para leer variables de entorno de Heroku
import json
import base64
from datetime import datetime
from discord.ext import commands
from discord import app_commands, Intents, Interaction, Object 
from discord.app_commands import Choice
import asyncio
from github import Github, InputGitAuthor

# =================================================================
# 🛑 CONFIGURACIÓN CRÍTICA (LEYENDO DESDE HEROKU CONFIG VARS) 🛑
# =================================================================
# ATENCIÓN: Los valores se leen de las "Config Vars" de Heroku (os.environ.get)
# No debes poner tus tokens aquí, solo Heroku los inyectará.

# 1. Token de tu bot de Discord 
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")

# 2. Tu Personal Access Token de GitHub 
GITHUB_PAT = os.environ.get("GITHUB_PAT")

# 3. Tu nombre de usuario de GitHub (este valor es fijo)
GITHUB_USER = "masterstudio-oficial" 

# 4. Nombre de tu repositorio (este valor es fijo)
GITHUB_REPO_NAME = "MasterStudio" 

# 5. ID de tu servidor de Discord (Se lee y se convierte a entero)
try:
    # Heroku guarda el ID como string, lo convertimos a int para Discord
    GUILD_ID = int(os.environ.get("GUILD_ID"))
except (TypeError, ValueError):
    # Si la variable no existe en Heroku, asumimos que no hay ID de servidor
    GUILD_ID = None

# Ruta del archivo JSON dentro del repositorio
JSON_FILE_PATH = "posts.json" 

# =================================================================
# CÓDIGO DEL BOT
# =================================================================

# Inicializar el bot de Discord con los Intents necesarios
intents = Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix="!", intents=intents)

# Inicializar la conexión con GitHub
# Se inicializa solo si los tokens existen (por si acaso Heroku no los carga)
if GITHUB_PAT and GITHUB_USER:
    g = Github(GITHUB_PAT)
    repo = g.get_user(GITHUB_USER).get_repo(GITHUB_REPO_NAME)
else:
    print("ERROR: Tokens de GitHub no cargados. El bot no podrá publicar.")
    g = None
    repo = None


@bot.event
async def on_ready():
    """Función que se ejecuta cuando el bot está listo y realiza una sincronización."""
    print(f'✅ Bot conectado como: {bot.user}')
    
    # Solo intentamos sincronizar si tenemos un ID de servidor válido
    if GUILD_ID:
        try:
            from discord import Object

            # 1. Limpieza de comandos antiguos
            bot.tree.clear_commands(guild=Object(id=GUILD_ID))
            await bot.tree.sync(guild=Object(id=GUILD_ID))
            print("Limpieza de comandos antiguos completada.")
            await asyncio.sleep(5) 

            # 2. Sincronización de comandos
            synced = await bot.tree.sync(guild=Object(id=GUILD_ID))
            
            print(f"Comandos sincronizados en el servidor {GUILD_ID}: {len(synced)}")
            print("Los comandos /post y /deletepost están registrados. ¡Listo para usar!")
            
        except Exception as e:
            print(f"Error al sincronizar comandos: {e}")
    else:
        print("Advertencia: GUILD_ID no configurado en Heroku. Los comandos de barra pueden no funcionar.")


# =================================================================
# FUNCIÓN UTILITARIA: SUBIR ARCHIVO DE TEXTO PLANO (CORREGIDA)
# =================================================================

def update_github_file(path, message, content, sha, interaction_user):
    """Sube contenido TEXTUAL (como JSON) a GitHub, asegurando la codificación correcta."""
    
    # Se utiliza esta función para subir el contenido como TEXTO plano (string)
    author = InputGitAuthor(
        interaction_user.name,
        f"{interaction_user.name}@masterstudio.com"
    )

    if repo:
        repo.update_file(
            path=path,
            message=message,
            content=content, # <--- El string JSON
            sha=sha, 
            branch="main",
            author=author
        )
    else:
        raise Exception("Repositorio de GitHub no inicializado. Revisa GITHUB_PAT.")


# =================================================================
# COMANDO DE BARRA /POST (PUBLICAR)
# =================================================================

@bot.tree.command(name="post", description="Crea una nueva publicación en la web de MasterStudio.") 
@app_commands.describe(
    titulo="Título del post (ej: Nueva Dificultad Extrema)",
    descripcion="Descripción detallada del cambio o post",
    url_imagen="URL de la imagen (debe ser permanente: Imgur, Discord CDN, etc.)", 
    es_nuevo="Marca si este post debe tener la etiqueta 'NEW!' (True/False)"
)
@app_commands.choices(
    categoria=[ 
        Choice(name="Cambio de dificultad", value="dificultad"),
        Choice(name="Mobs nuevos", value="mobs"),
        Choice(name="Eventos", value="eventos"),
        Choice(name="Actualizaciones", value="actualizaciones"),
        Choice(name="Recompensas", value="recompensas"),
        Choice(name="Castigos", value="castigos"),
    ]
)
async def post_command(
    interaction: Interaction, 
    categoria: Choice[str], 
    titulo: str, 
    descripcion: str, 
    url_imagen: str, 
    es_nuevo: bool = True
):
    """Maneja el comando /post, insertando la URL de imagen directamente en el JSON."""
    
    await interaction.response.send_message("⚙️ Procesando publicación... iniciando conexión con GitHub.", ephemeral=True)

    def github_task():
        if not repo:
            raise Exception("Repositorio no accesible.")

        # 1. OBTENER CONTENIDO (DECODIFICAR)
        contents = repo.get_contents(JSON_FILE_PATH, ref="main")
        
        # OBTENEMOS EL CONTENIDO COMO TEXTO PLANO
        encoded_content_from_github = contents.content 
        decoded_content = base64.b64decode(encoded_content_from_github).decode('utf-8')
        posts_list = json.loads(decoded_content) # <--- Intenta cargar el JSON

        # 2. CREAR NUEVO POST
        new_post = {
            "id": len(posts_list) + 1,
            "categoria": categoria.value, 
            "titulo": titulo,
            "descripcion": descripcion,
            "fecha": datetime.now().strftime("%Y-%m-%d"), 
            "imagenUrl": url_imagen, 
            "esNuevo": es_nuevo
        }

        posts_list.insert(0, new_post)
        
        # 3. CODIFICAR CONTENIDO DE VUELTA A STRING JSON
        updated_content_string = json.dumps(posts_list, indent=4, ensure_ascii=False)
        
        # 4. SUBIR A GITHUB USANDO LA FUNCIÓN SEGURA
        update_github_file(
            path=JSON_FILE_PATH,
            message=f"Bot: Nuevo post '{titulo}' añadido por {interaction.user.name}",
            content=updated_content_string, 
            sha=contents.sha, 
            interaction_user=interaction.user
        )
        
        return categoria.name

    try:
        loop = asyncio.get_event_loop()
        categoria_nombre = await loop.run_in_executor(None, github_task)
        
        await interaction.edit_original_response(
            content=f"🚀 ¡Publicación exitosa! **'{titulo}'** ha sido añadida. Verifica tu web."
        )

    except json.JSONDecodeError as e:
         await interaction.edit_original_response(
            content=f"❌ ¡Error al publicar! El archivo posts.json no es JSON válido. Arréglalo manualmente a `[]` en GitHub. Error: {e}"
        )
    except Exception as e:
        print(f"Error durante el proceso de publicación: {e}")
        await interaction.edit_original_response(
            content=f"❌ ¡Error al publicar! No se pudo actualizar el JSON. Error: {e}"
        )


# =================================================================
# COMANDO DE BARRA /DELETEPOST (ELIMINAR)
# =================================================================

@bot.tree.command(name="deletepost", description="Elimina una publicación por su título exacto.")
@app_commands.describe(
    titulo="El título EXACTO del post que quieres eliminar (ej: Nueva Dificultad Extrema)"
)
async def delete_post_command(interaction: Interaction, titulo: str):
    """Maneja el comando /deletepost."""
    
    await interaction.response.send_message(f"⚙️ Buscando y eliminando el post con título: **'{titulo}'**...", ephemeral=True)

    def github_delete_task():
        if not repo:
            raise Exception("Repositorio no accesible.")
            
        # 1. OBTENER CONTENIDO (DECODIFICAR)
        contents = repo.get_contents(JSON_FILE_PATH, ref="main")
        encoded_content_from_github = contents.content 
        decoded_content = base64.b64decode(encoded_content_from_github).decode('utf-8')
        
        try:
            posts_list = json.loads(decoded_content)
        except json.JSONDecodeError:
            # Si está corrupto, lo detectamos
            raise json.JSONDecodeError("El archivo posts.json está corrupto y no se puede leer.", "", 0)

        # 2. ENCONTRAR Y ELIMINAR EL POST
        initial_count = len(posts_list)
        new_posts_list = [post for post in posts_list if post.get('titulo') != titulo]
        final_count = len(new_posts_list)
        
        if initial_count == final_count:
            return False, "Error: No se encontró ningún post con ese título exacto. (Verifique mayúsculas y minúsculas)"

        # 3. SUBIR EL CONTENIDO MODIFICADO (A STRING JSON)
        updated_content_string = json.dumps(new_posts_list, indent=4, ensure_ascii=False)
        
        # 4. SUBIR A GITHUB USANDO LA FUNCIÓN SEGURA
        update_github_file(
            path=JSON_FILE_PATH,
            message=f"Bot: Eliminado el post '{titulo}' por {interaction.user.name}",
            content=updated_content_string,
            sha=contents.sha, 
            interaction_user=interaction.user
        )
        
        return True, "El post fue eliminado exitosamente."

    try:
        loop = asyncio.get_event_loop()
        success, message = await loop.run_in_executor(None, github_delete_task)
        
        if success:
            await interaction.edit_original_response(
                content=f"🗑️ ¡Eliminación exitosa! El post **'{titulo}'** ha sido eliminado de la web. Verifica tu página."
            )
        else:
            await interaction.edit_original_response(
                content=f"❌ No se pudo eliminar el post. {message}"
            )

    except json.JSONDecodeError:
        await interaction.edit_original_response(
            content=f"❌ ¡Error al eliminar! El archivo posts.json no es JSON válido. Arréglalo manualmente a `[]` en GitHub."
        )
    except Exception as e:
        print(f"Error durante el proceso de eliminación en GitHub: {e}")
        await interaction.edit_original_response(
            content=f"❌ ¡Error crítico al intentar eliminar! Revisa la consola. Error: {e}"
        )


# =================================================================
# INICIAR EL BOT
# =================================================================

if __name__ == "__main__":
    if DISCORD_BOT_TOKEN:
        bot.run(DISCORD_BOT_TOKEN)
    else:
        print("ERROR: DISCORD_BOT_TOKEN no se pudo cargar. El bot no se iniciará.")
