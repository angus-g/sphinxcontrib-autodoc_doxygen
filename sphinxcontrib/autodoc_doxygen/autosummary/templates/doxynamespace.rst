.. autodoxymodule:: {{ fullname }}
   :members:

   {% if types %}
   ----------
   Data Types
   ----------

   .. autodoxysummary::

   {% for item in types %}
      ~{{ item }}
   {%- endfor %}
   {% endif %}

   {% if methods %}
   ---------------------
   Functions/Subroutines
   ---------------------

   .. autodoxysummary::
   {% for item in methods %}
      ~{{ fullname }}::{{ item }}
   {%- endfor %}
   {% endif %}
